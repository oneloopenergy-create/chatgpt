from fastapi.testclient import TestClient

from gridease.api import app as appmod
from gridease.core.store import ProjectStore

from .conftest import BRIEF


def test_api_flow(tmp_path):
    appmod._store = ProjectStore(tmp_path)
    c = TestClient(appmod.app)
    assert c.get("/").status_code == 200
    p = c.post("/api/projects", json={"name": "API test", "brief": BRIEF}).json()
    pid = p["id"]
    assert p["params"]["site.dnsp"]["value"] == "Ausgrid"
    assert c.put(f"/api/projects/{pid}/params/calc.inverter_ac_kva", json={"value": 1}).status_code == 400
    for k, v in {"site.customer": "Demo", "site.address": "1 Rd", "contractor.licence_no": "EC1"}.items():
        c.put(f"/api/projects/{pid}/params/{k}", json={"value": v})
    r = c.post(f"/api/projects/{pid}/documents/generate").json()
    assert "sld" in r["generated"]
    svg = c.get(f"/api/projects/{pid}/documents/sld")
    assert svg.status_code == 200 and "<svg" in svg.text
    assert c.get(f"/api/projects/{pid}/package?mode=final").status_code == 409
    z = c.get(f"/api/projects/{pid}/package?mode=draft")
    assert z.status_code == 200 and z.content[:2] == b"PK"
    assert c.delete(f"/api/projects/{pid}").status_code == 204
    assert c.get(f"/api/projects/{pid}").status_code == 404


def test_rules_and_sources_api(tmp_path):
    appmod._store = ProjectStore(tmp_path)
    c = TestClient(appmod.app)
    r = c.post("/api/rules/evaluate", json={"dnsp": "Ausgrid", "generation_kw": 350, "aggregate_inverter_kva": 400,
                                            "aemo_registration_status": "exempt", "existing_eg_present": False}).json()
    assert r["status"] == "preliminary_only" and "nonregistered_path" in r["flags"]
    assert r["fired"][0]["source_docs"][0]["url"].startswith("https://www.ausgrid.com.au")
    src = c.get("/api/sources").json()
    assert len(src["nsw_sources"]["sources"]) == 16 and src["nsw_sources"]["sources"][0]["id"] == "SRC001"
    ev = src["dnsp_evidence"]
    assert {s["source_id"] for s in ev["sources"]} >= {"AUS-NS194", "END-PDIA", "QLD-STNW1175"}
    assert all(f["maps_to"] for f in ev["field_vocabulary"])
    pid = c.post("/api/projects", json={"name": "x", "brief": BRIEF}).json()["id"]
    pr = c.get(f"/api/projects/{pid}/rules").json()
    assert "AG-R002" in pr["rule_ids"] and pr["fields"]["aggregate_inverter_kva"] == 1080
