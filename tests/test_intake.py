from gridease.intake.extract import RuleExtractor

from .conftest import BRIEF


def test_extracts_fields_with_evidence():
    r = {f.key: f for f in RuleExtractor().extract(BRIEF).fields}
    assert r["site.dnsp"].value == "Ausgrid"
    assert r["site.nmi"].value == "4103123456"
    assert r["pv.dc_kwp"].value == 800
    assert r["export.requested_kw"].value == 150
    assert r["connection.supply_voltage_v"].value == 400
    invs = {i["model"]: i["qty"] for i in r["equipment.pv_inverters"].value}
    assert invs == {"STP 110-60": 3, "SG250HX": 2}
    bess = r["equipment.bess"].value[0]
    assert bess["qty"] == 2 and bess["energy_kwh"] == 250
    assert r["design.topology"].value == "pv_bess_ac_coupled"


def test_mv_and_zero_export():
    r = {f.key: f.value for f in RuleExtractor().extract("Energex 22 kV connection, kiosk transformer 2000 kVA, ground-mounted PV 1800 kWp, zero export").fields}
    assert r["connection.supply_voltage_v"] == 22000
    assert r["connection.transformer_kva"] == 2000
    assert r["export.requested_kw"] == 0
    assert r["design.topology"] == "mv_kiosk"


def test_extracted_values_need_confirmation(project):
    assert project.params["pv.dc_kwp"].is_assumption
    assert not project.params["site.customer"].is_assumption


def test_extracts_distinct_capacity_and_registration_fields():
    text = ("Ausgrid, max generation 950 kW, exempt from AEMO registration, no existing solar, ABN 12 345 678 901, "
            "battery charge 250 kW, discharge 250 kW")
    r = {f.key: f.value for f in RuleExtractor().extract(text).fields}
    assert r["generation.max_kw"] == 950
    assert r["registration.aemo_status"] == "exempt"
    assert r["site.existing_eg_present"] is False
    assert r["site.applicant_abn"] == "12345678901"
    assert r["bess.charge_kw"] == 250 and r["bess.discharge_kw"] == 250


def test_extracts_dates_class_and_scr():
    text = ("Energex 11 kV, class A2, SCR 2.5, connection agreement signed 2027-02-01, "
            "approved 2026-10-01, commissioning 2027-06-30, site in Brisbane QLD 4000")
    r = {f.key: f.value for f in RuleExtractor().extract(text).fields}
    assert r["connection.eg_class"] == "A2" and r["connection.scr"] == 2.5
    assert r["project.connection_agreement_date"] == "2027-02-01"
    assert r["project.dnsp_approval_date"] == "2026-10-01"
    assert r["project.commissioning_date"] == "2027-06-30"
    assert r["site.postcode"] == "4000"
