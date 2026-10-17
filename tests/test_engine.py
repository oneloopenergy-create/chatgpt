import pytest

from gridease.calc.bess import size_bess
from gridease.calc.engineering import protection_settings, run_all
from gridease.compliance.checks import run_checks
from gridease.core.model import SignOff, SourceKind
from gridease.package.bundle import PackageBlocked, build_package
from gridease.package.documents import generate_all
from gridease.rules.library import load_pack

from .conftest import user


def test_capacity_and_path(project):
    assert project.get("calc.pv_inverter_ac_kva") == 830  # 3 x 110 + 2 x 250
    assert project.get("calc.bess_pcs_kva") == 250
    assert project.get("calc.inverter_ac_kva") == 1080
    assert project.get("calc.connection_path") == "LV"
    assert project.get("calc.central_protection_required") is True
    # Ausgrid 30 kW option only applies to >30–200 kVA (AG-R011); 1080 kVA needs assessment
    assert project.get("export.scheme") == "requires_dnsp_assessment"
    assert project.get("calc.connection_phase") == "LV"
    assert project.get("calc.export_limiting_required") is True
    assert project.get("calc.rated_current_a") == pytest.approx(1558.8, abs=0.1)


def test_every_value_has_traceable_source(project):
    for p in project.params.values():
        assert p.source.ref
    calc = project.params["calc.inverter_ac_kva"]
    assert calc.source.kind == SourceKind.CALCULATION
    assert "equipment.pv_inverters@v" in calc.source.ref
    assert project.params["rules.central_protection_above_kva"].source.ref.startswith("rule:dnsp_ausgrid@")


def test_rerun_is_idempotent(project):
    versions = {k: v.version for k, v in project.params.items()}
    run_all(project)
    assert versions == {k: v.version for k, v in project.params.items()}


def test_protection_table_includes_central_protection(project):
    rows = protection_settings(project)
    central = [r for r in rows if r["location"].startswith("Central protection")]
    assert {r["ansi"] for r in central} == {"59", "27", "81O", "81U"}
    # values not yet extracted from NS194: never invented
    assert all(r["setting"].startswith("TBC") for r in central)
    assert not any(r["ansi"] == "59N" for r in rows)  # 59N is MV only


def test_findings_are_explainable(project):
    ids = {f.id: f for f in run_checks(project)}
    assert "prot.central" in ids and "export.device" in ids
    f = ids["prot.central"]
    assert f.clause.startswith("rule:dnsp_ausgrid") and f.params and f.suggestion


def test_non_cec_inverter_is_error(project):
    user(project, "equipment.pv_inverters", [{"manufacturer": "Acme", "model": "X1", "rated_ac_kva": 100, "qty": 1}])
    run_all(project)
    assert any(f.id == "cec.missing.X1" and f.severity == "error" for f in run_checks(project))


def test_param_change_marks_documents_stale(project):
    done, errors = generate_all(project)
    assert not errors, errors
    assert project.stale_documents() == []
    user(project, "export.requested_kw", 100)
    run_all(project)
    stale = set(project.stale_documents())
    assert {"application_form", "export_scheme", "sld"} <= stale
    assert "protection_settings" not in stale


def test_signoff_invalidated_by_change(project):
    generate_all(project)
    project.sign(SignOff(reviewer_name="Jane Eng", registration_type="NER", registration_no="123456",
                         scope=["sld", "protection_settings"]))
    assert project.is_signed("sld")
    user(project, "site.nmi", "4103999999")
    generate_all(project)
    assert not project.is_signed("sld")
    assert project.is_signed("protection_settings")


def test_cannot_sign_stale_document(project):
    generate_all(project)
    user(project, "site.nmi", "4103999999")
    with pytest.raises(ValueError):
        project.sign(SignOff(reviewer_name="J", registration_type="RPEQ", registration_no="1", scope=["sld"]))


def test_final_package_gating(project, monkeypatch):
    generate_all(project)
    with pytest.raises(PackageBlocked) as e:
        build_package(project, "final")
    assert any("signed off" in b for b in e.value.blockers)
    assert build_package(project, "draft")[:2] == b"PK"

    user(project, "design.central_protection_relay", "SEL-751")
    user(project, "design.export_limiter", "Solar Analytics EL-3")
    user(project, "generation.max_kw", 1000, "kW")
    user(project, "site.existing_eg_present", False)
    run_all(project)
    for a in project.assumptions():
        project.confirm_param(a.key, "Jane Eng")
    generate_all(project)
    project.sign(SignOff(reviewer_name="Jane Eng", registration_type="NER", registration_no="123456",
                         scope=["sld", "protection_settings"]))
    with pytest.raises(PackageBlocked) as e:  # placeholder rule packs cannot be used for a final package
        build_package(project, "final")
    assert any("rules.unverified" in b for b in e.value.blockers)
    monkeypatch.setitem(load_pack("dnsp_ausgrid"), "verified", True)
    with pytest.raises(PackageBlocked) as e:
        build_package(project, "final")
    assert any("unresolved review" in b for b in e.value.blockers)
    for key, value in {
        "site.applicant_abn": "12345678901", "site.existing_eg_kva": 0,
        "registration.aemo_status": "exempt", "bess.charge_kw": 250,
        "bess.discharge_kw": 250, "connection.max_import_kw": 600,
        "site.survey_kmz": "verified-survey.kmz",
    }.items():
        user(project, key, value)
    # Explicit array allocations, rather than invented shares of total project kWp.
    user(project, "equipment.pv_inverters", [inv | {"dc_kwp": dc} for inv, dc in
         zip(project.get("equipment.pv_inverters"), [300, 500])])
    run_all(project)
    generate_all(project)
    project.sign(SignOff(reviewer_name="Jane Eng", registration_type="NER", registration_no="123456",
                         scope=["sld", "protection_settings"]))
    assert build_package(project, "final")[:2] == b"PK"


def test_bess_sizing(project):
    res = size_bess(project)
    assert res["options"] and res["recommended"]
    assert project.params["bess.capex_per_kwh"].is_assumption
    assert project.get("calc.bess_recommended_kwh") == res["recommended"]["energy_kwh"]


def test_rfi_impact(project):
    from gridease.core.model import RfiItem
    generate_all(project)
    r = project.open_rfi([RfiItem(text="Please reduce the export limit", affected_params=["export.requested_kw"])])
    assert "export_scheme" in project.rfi_affected_documents(r.round_no)
