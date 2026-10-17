"""Ausgrid rule pack v0.2: test cases from GridEasy_Ausgrid_Rule_Pack_v0.2.xlsx (Test_Cases sheet)
and the smoke checks from ausgrid_rule_engine_seed.py."""
import pytest

from gridease.compliance.checks import run_checks
from gridease.rules.engine import evaluate_fields
from gridease.rules.library import load_pack

from .conftest import user

# (test id, input, expected rule ids ⊆ fired, expected flags ⊆ flags, rule ids that must NOT fire)
WORKBOOK_CASES = [
    ("T01", {"dnsp": "Ausgrid", "generation_kw": 350, "aggregate_inverter_kva": 400, "aemo_registration_status": "exempt",
             "existing_eg_present": False},
     {"AG-R001", "AG-R002", "AG-R003", "AG-R004"}, {"nonregistered_path", "interface_protection_required"}, set()),
    ("T02", {"dnsp": "Ausgrid", "generation_kw": 150, "aggregate_inverter_kva": 180, "existing_eg_present": True},
     {"AG-R004"}, {"existing_eg_details_required"}, {"AG-R001", "AG-R002", "AG-R003"}),
    ("T03", {"dnsp": "Ausgrid", "generation_kw": 800, "aggregate_inverter_kva": 900, "connection_phase": "HV",
             "aemo_registration_status": "unknown"},
     {"AG-R002", "AG-R003", "AG-R007"}, {"registration_status_review", "hv_review"}, {"AG-R001"}),
    ("T04", {"dnsp": "Ausgrid", "generation_kw": 4990, "aggregate_inverter_kva": 5100, "aemo_registration_status": "unknown"},
     {"AG-R002", "AG-R003"}, {"capacity_boundary_review"}, {"AG-R001"}),
]


@pytest.mark.parametrize("tid,fields,rules,flags,not_rules", WORKBOOK_CASES, ids=[c[0] for c in WORKBOOK_CASES])
def test_workbook_cases(tid, fields, rules, flags, not_rules):
    ev = evaluate_fields(fields)
    assert ev.status == "preliminary_only"
    assert rules <= set(ev.rule_ids), f"{tid}: missing {rules - set(ev.rule_ids)}"
    assert flags <= set(ev.flags), f"{tid}: missing {flags - set(ev.flags)}"
    assert not (not_rules & set(ev.rule_ids)), f"{tid}: unexpected {not_rules & set(ev.rule_ids)}"


def test_t05_ausgrid_pack_never_runs_on_other_dnsp():
    ev = evaluate_fields({"dnsp": "Endeavour", "generation_kw": 500, "aggregate_inverter_kva": 550},
                         pack=load_pack("dnsp_ausgrid"))
    assert ev.status == "unsupported_dnsp" and ev.fired == []


def test_endeavour_pdi5000_lv_scope():
    ev = evaluate_fields({"dnsp": "Endeavour Energy", "connection_phase": "LV", "aggregate_inverter_kva": 550, "bess_pcs_kva": 100})
    assert {"EE-001", "EE-002", "EE-003"} <= set(ev.rule_ids)
    ev = evaluate_fields({"dnsp": "Endeavour Energy", "connection_phase": "LV", "aggregate_inverter_kva": 400})
    assert "EE-001" in ev.rule_ids and "EE-002" not in ev.rule_ids
    assert not {"EE-001", "EE-002"} & set(evaluate_fields({"dnsp": "Endeavour Energy", "connection_phase": "HV",
                                                            "aggregate_inverter_kva": 2000}).rule_ids)


def test_seed_script_smoke_checks():
    # interface protection is strictly > 200 kVA (NS194 §5.4.2)
    assert "interface_protection_required" in evaluate_fields({"dnsp": "Ausgrid", "aggregate_inverter_kva": 400}).flags
    assert "interface_protection_required" not in evaluate_fields({"dnsp": "Ausgrid", "aggregate_inverter_kva": 200}).flags
    ev = evaluate_fields({"dnsp": "Ausgrid", "aggregate_inverter_kva": 400})
    assert "missing_existing_eg_declaration" in ev.flags and "registration_status_review" in ev.flags


def test_kw_and_kva_are_not_conflated():
    # pathway uses generation kW; protection uses inverter kVA
    ev = evaluate_fields({"dnsp": "Ausgrid", "generation_kw": 190, "aggregate_inverter_kva": 220,
                          "aemo_registration_status": "exempt"})
    assert "AG-R002" in ev.rule_ids and "AG-R001" not in ev.rule_ids
    assert "capacity_boundary_review" in ev.flags


def test_every_rule_cites_a_known_source():
    pack = load_pack("dnsp_ausgrid")
    for r in pack["rules"]:
        for sid in str(r["source"]).split(";"):
            assert sid in pack["sources"], (r["id"], sid)
            assert pack["sources"][sid]["url"].startswith("https://")


def test_rules_surface_as_cited_findings(project):
    ids = {f.id: f for f in run_checks(project)}
    assert "AG-R002" in ids and "NS194" in ids["AG-R002"].clause and "https://www.ausgrid.com.au" in ids["AG-R002"].clause
    assert ids["AG-R010"].severity == "error"          # generation kW not entered separately
    user(project, "generation.max_kw", 1000, "kW")
    assert "AG-R010" not in {f.id for f in run_checks(project)}


def test_unsourced_dnsp_values_are_reported_not_invented(project):
    from gridease.calc.engineering import run_all
    user(project, "site.dnsp", "Endeavour Energy")
    run_all(project)
    assert project.get("calc.central_protection_required") is None
    ids = {f.id for f in run_checks(project)}
    assert {"prot.threshold_unsourced", "4777.region_unsourced", "EE-001", "EE-002"} <= ids


SMALL_PV = {"dnsp": "Ausgrid", "pv_dc_kwp": 120, "aggregate_inverter_kva": 100, "generation_kw": 100}


@pytest.mark.parametrize("commissioning,expected,absent", [
    ("2026-11-01", set(), {"AUS-EB-001", "AUS-EB-002", "AUS-EB-003"}),
    ("2026-12-01", {"AUS-EB-001", "AUS-EB-002"}, {"AUS-EB-003"}),
    ("2027-03-01", {"AUS-EB-001", "AUS-EB-002", "AUS-EB-003"}, set()),
    (None, {"AUS-EB-001", "AUS-EB-002", "AUS-EB-003"}, set()),  # unknown date: review, never assume exempt
])
def test_emergency_backstop_is_date_dependent(commissioning, expected, absent):
    f = dict(SMALL_PV) | ({"commissioning_date": commissioning} if commissioning else {})
    ids = set(evaluate_fields(f).rule_ids)
    assert expected <= ids and not (absent & ids)


def test_emergency_backstop_reapplication_and_size_scope():
    f = SMALL_PV | {"dnsp_approval_date": "2026-10-01"}
    assert "AUS-EB-004" in evaluate_fields(f).rule_ids
    assert "AUS-EB-004" not in evaluate_fields(f | {"commissioning_date": "2027-04-01"}).rule_ids
    big = {"dnsp": "Ausgrid", "pv_dc_kwp": 800, "aggregate_inverter_kva": 1080, "generation_kw": 950}
    assert not any(r.startswith("AUS-EB") for r in evaluate_fields(big).rule_ids)


def test_essential_scada_depends_on_connection_agreement_date():
    hv = {"dnsp": "Essential Energy", "connection_phase": "HV", "generation_kw": 3000}
    assert "ESS-HV-001" not in evaluate_fields(hv | {"connection_agreement_date": "2026-12-01"}).rule_ids
    assert "ESS-HV-001" in evaluate_fields(hv | {"connection_agreement_date": "2027-01-05"}).rule_ids
    assert {"ESS-HV-001", "ES-001", "ES-R008"} <= set(evaluate_fields(hv).rule_ids)


def test_qld_emt_model_is_not_unconditional():
    hv = {"dnsp": "Energex", "connection_phase": "HV"}
    a2 = hv | {"class_a1_a2_b": "A2"}
    ids = set(evaluate_fields(a2 | {"standby_or_bumpless": False, "synchronous_rotating_machine": False}).rule_ids)
    assert "QLD-HV-001" in ids and "QLD-HV-001X" not in ids
    ids = set(evaluate_fields(a2).rule_ids)                     # exceptions not determined
    assert "QLD-HV-001X" in ids and "QLD-HV-001" not in ids
    ids = set(evaluate_fields(a2 | {"standby_or_bumpless": True, "synchronous_rotating_machine": False}).rule_ids)
    assert not {"QLD-HV-001", "QLD-HV-001X"} & ids            # exception applies
    assert "QLD-HV-002" in evaluate_fields(hv | {"class_a1_a2_b": "A1", "scr": 2.5}).rule_ids
    assert {"QLD-HV-003", "QLD-HV-004", "QLD-HV-005"} <= set(evaluate_fields({"dnsp": "Ergon", "connection_phase": "HV"}).rule_ids)


def test_qld_lv_reports_coverage_gap(project):
    from gridease.calc.engineering import run_all
    user(project, "site.dnsp", "Energex")
    run_all(project)
    assert "rules.coverage_gap" in {f.id for f in run_checks(project)}


def test_postcode_derived_from_address(project):
    from gridease.calc.engineering import run_all
    run_all(project)
    assert project.get("site.postcode") is None  # "Smithfield NSW" has no postcode in the fixture
    user(project, "site.address", "1 Example Rd, Smithfield NSW 2164")
    run_all(project)
    assert project.get("site.postcode") == "2164"
