"""Declarative rule engine for DNSP rule packs.

Rules are data (YAML), not code: each has an id, a condition tree (``when``), the outcome text, the source
document and clause it cites, an automated action, an optional review flag and a severity. A pack only
evaluates projects in its own DNSP; anything else returns ``unsupported_dnsp``.

Conditions are evaluated against a flat field dictionary in the rule-pack vocabulary (``FIELD_MAP``),
which keeps kW, kVA and kWh quantities as distinct fields. Comparisons work on numbers and on ISO dates
(YYYY-MM-DD), so time-dependent rules (e.g. NSW Emergency Backstop phase-in) can key off project dates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..core.model import Project
from .library import RulePack, dnsp_pack

# rule-pack field -> project parameter key
FIELD_MAP: dict[str, str] = {
    "dnsp": "site.dnsp",
    "site_address": "site.address",
    "applicant_name": "site.customer",
    "applicant_abn": "site.applicant_abn",
    "connection_voltage_v": "connection.supply_voltage_v",
    "connection_phase": "calc.connection_phase",
    "existing_eg_present": "site.existing_eg_present",
    "existing_eg_kva": "site.existing_eg_kva",
    "pv_dc_kwp": "pv.dc_kwp",
    "pv_inverter_kva": "calc.pv_inverter_ac_kva",
    "bess_energy_kwh": "calc.bess_energy_kwh",
    "bess_pcs_kva": "calc.bess_pcs_kva",
    "bess_charge_kw": "bess.charge_kw",
    "bess_discharge_kw": "bess.discharge_kw",
    "aggregate_inverter_kva": "calc.inverter_ac_kva",
    "generation_kw": "generation.max_kw",
    "export_limit_kw": "export.requested_kw",
    "max_import_kw": "connection.max_import_kw",
    "aemo_registration_status": "registration.aemo_status",
    # Evidence Pack v0.4 canonical keys
    "nmi": "site.nmi",
    "postcode": "site.postcode",
    "voltage_kv": "calc.connection_voltage_kv",
    "phase_count": "connection.phase_count",
    "ies_total_kva": "calc.inverter_ac_kva",
    "pv_dc_kw": "pv.dc_kwp",
    "battery_power_kw": "calc.bess_pcs_kva",
    "battery_energy_kwh": "calc.bess_energy_kwh",
    "export_control_method": "export.scheme",
    "application_type": "project.application_type",
    "connection_agreement_date": "project.connection_agreement_date",
    "dnsp_approval_date": "project.dnsp_approval_date",
    "commissioning_date": "project.commissioning_date",
    "class_a1_a2_b": "connection.eg_class",
    "scr": "connection.scr",
    "standby_or_bumpless": "design.standby_or_bumpless",
    "synchronous_rotating_machine": "design.synchronous_rotating_machine",
    "pscad_model_available": "design.pscad_model_available",
    "scada_rtu": "design.scada_rtu",
    "rpeq_name": "signoff.rpeq_name",
    "rpeq_registration": "signoff.rpeq_registration",
    "connection_point": "site.connection_point",
    "technology": "design.topology",
    "grid_model_available": "design.grid_model_available",
    "metering_scheme": "design.metering_scheme",
    "inverter_make_model": "equipment.pv_inverters",
    "pcs_make_model": "equipment.bess",
    "battery_make_model": "equipment.bess",
    "protection_design": "design.central_protection_relay",
    "cyber_security_assessment": "design.cyber_security_assessment",
    "sld_file": "doc:sld",  # a generated document, not a parameter
}

REGISTRATION_STATUSES = ("registered", "exempt", "pending", "unknown")


@dataclass
class FiredRule:
    id: str
    trigger: str
    outcome: str
    action: str
    flag: str | None
    severity: str
    source_id: str
    source_docs: list[dict[str, Any]]
    clause: str
    confidence: str
    engineering_review: str
    fields: list[str]
    effective_from: str | None = None
    notes: str | None = None

    @property
    def citation(self) -> str:
        docs = "; ".join(d["document"] for d in self.source_docs) or self.source_id
        return f"{self.id} · {docs} · {self.clause} ({self.confidence})"


@dataclass
class Evaluation:
    status: str  # preliminary_only | unsupported_dnsp | no_rule_pack
    pack: str | None = None
    fired: list[FiredRule] = field(default_factory=list)

    @property
    def rule_ids(self) -> list[str]:
        return [r.id for r in self.fired]

    @property
    def flags(self) -> list[str]:
        return [r.flag for r in self.fired if r.flag]


def _leaf(cond: dict[str, Any], f: dict[str, Any]) -> bool:
    v = f.get(cond["field"])
    op, ref = cond["op"], cond.get("value")
    if op == "present":
        return v is not None
    if op == "missing":
        return v is None
    if v is None:
        return False
    if isinstance(v, (str, date)) and isinstance(ref, (str, date)) and op in ("gt", "gte", "lt", "lte"):
        a, b = str(v)[:10], str(ref)[:10]  # ISO dates compare correctly as strings
        return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[op]
    try:
        return {
            "eq": lambda: v == ref, "ne": lambda: v != ref,
            "in": lambda: v in ref, "not_in": lambda: v not in ref,
            "gt": lambda: float(v) > float(ref), "gte": lambda: float(v) >= float(ref),
            "lt": lambda: float(v) < float(ref), "lte": lambda: float(v) <= float(ref),
        }[op]()
    except (TypeError, ValueError):
        return False


def matches(cond: dict[str, Any], f: dict[str, Any]) -> bool:
    if "all" in cond:
        return all(matches(c, f) for c in cond["all"])
    if "any" in cond:
        return any(matches(c, f) for c in cond["any"])
    return _leaf(cond, f)


def _fields_in(cond: dict[str, Any]) -> list[str]:
    if "all" in cond or "any" in cond:
        return sorted({x for c in cond.get("all", cond.get("any", [])) for x in _fields_in(c)})
    return [cond["field"]]


def evaluate_fields(f: dict[str, Any], pack: RulePack | None = None) -> Evaluation:
    """Evaluate a flat field dict (rule-pack vocabulary)."""
    dnsp = f.get("dnsp")
    if pack is None:
        try:
            pack = dnsp_pack(dnsp or "")
        except (KeyError, AttributeError):
            return Evaluation(status="unsupported_dnsp")
    if not pack.get("rules"):
        return Evaluation(status="no_rule_pack", pack=pack["id"])
    try:
        same = dnsp_pack(dnsp or "")["id"] == pack["id"]  # resolves aliases, e.g. "Ergon" / "Ergon Energy Network"
    except (KeyError, AttributeError):
        same = False
    if not same:
        return Evaluation(status="unsupported_dnsp", pack=pack["id"])
    out = Evaluation(status="preliminary_only", pack=pack["id"])
    sources = pack.get("sources", {})
    for r in pack["rules"]:
        if not matches(r["when"], f):
            continue
        sid = str(r["source"])
        out.fired.append(FiredRule(
            id=r["id"], trigger=r["trigger"], outcome=r["outcome"], action=r["action"], flag=r.get("flag"), severity=r["severity"],
            source_id=sid, source_docs=[{"id": s, **sources[s]} for s in sid.split(";") if s in sources],
            clause=str(r["clause"]), confidence=r["confidence"], engineering_review=str(r["engineering_review"]),
            fields=_fields_in(r["when"]),
            effective_from=str(r["effective_from"]) if r.get("effective_from") else None, notes=r.get("notes"),
        ))
    return out


def project_fields(p: Project) -> tuple[dict[str, Any], dict[str, int]]:
    """Map project parameters to rule-pack fields; also returns the parameter versions used."""
    f, used = {}, {}
    for name, key in FIELD_MAP.items():
        prm = p.params.get(key)
        if prm is not None:
            f[name] = prm.value
            used[key] = prm.version
    return f, used


def evaluate_project(p: Project) -> Evaluation:
    if p.get("site.dnsp") is None:
        return Evaluation(status="unsupported_dnsp")
    f, _ = project_fields(p)
    return evaluate_fields(f)
