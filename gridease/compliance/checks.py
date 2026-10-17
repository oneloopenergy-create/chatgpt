"""Compliance and export-limit checks.

Every finding is expandable: the clause it relies on, the parameters involved, what is wrong (detail),
and how to fix it (suggestion).
severity: error = blocks the final package; warning = engineer judgement required; info = reminder.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

from ..core.model import Project
from ..rules.engine import FIELD_MAP, evaluate_project
from ..rules.library import find_cec_inverter, load_pack


class Finding(BaseModel):
    id: str
    severity: Literal["error", "warning", "info"]
    title: str
    clause: str
    params: list[str]
    detail: str
    suggestion: str


REQUIRED_INPUTS = [
    "site.customer", "site.address", "site.nmi", "site.dnsp", "connection.supply_voltage_v",
    "connection.max_demand_kva", "pv.dc_kwp", "equipment.pv_inverters", "export.requested_kw",
    "design.topology", "contractor.licence_no",
]


def run_checks(p: Project, today: date | None = None) -> list[Finding]:
    today = today or date.today()
    f: list[Finding] = []
    add = lambda **kw: f.append(Finding(**kw))  # noqa: E731

    # 1. Required application inputs
    missing = [k for k in REQUIRED_INPUTS if p.get(k) in (None, "", [])]
    if missing:
        add(id="input.missing", severity="error", title=f"{len(missing)} required application input(s) missing",
            clause="DNSP application form mandatory fields", params=missing,
            detail="Not yet entered: " + ", ".join(missing),
            suggestion="Complete them in step 1, or upload bills/datasheets for automatic extraction.")

    # 2. Connection path
    path = p.get("calc.connection_path")
    kva = p.get("calc.inverter_ac_kva")
    if path == "small_out_of_scope":
        add(id="path.small", severity="error", title="Systems of 30 kVA or less are outside the MVP scope",
            clause="ENA DER guidelines · small EG category", params=["calc.inverter_ac_kva"],
            detail=f"Total inverter capacity {kva} kVA ≤ 30 kVA; the small EG process applies.",
            suggestion="Apply through the DNSP's small EG online process.")
    elif path == "path_b_nem_registered":
        add(id="path.b", severity="error", title="Above 5 MW: AEMO registration path required (phase 3)",
            clause="AEMO generator registration exemption guide; NER Chapter 5", params=["calc.inverter_ac_kva"],
            detail=f"Total inverter capacity {kva} kVA > 5000 kVA.",
            suggestion="Split the project or wait for the GPS assistant.")
    if path == "LV" and kva is not None and p.get("rules.lv_max_kva") is not None \
            and float(kva) > float(p.get("rules.lv_max_kva")):
        add(id="path.lv_limit", severity="warning", title="LV connection exceeds the DNSP's LV capacity limit",
            clause=f"{p.params['rules.lv_max_kva'].source.ref}", params=["calc.inverter_ac_kva", "rules.lv_max_kva"],
            detail=f"{kva} kVA > LV limit {p.get('rules.lv_max_kva')} kVA.",
            suggestion="Consider an MV connection (dedicated kiosk), or raise it with the DNSP early.")

    # 3. CEC listing and AS/NZS 4777.2
    for key in ("equipment.pv_inverters", "equipment.bess"):
        for item in p.get(key) or []:
            model = item.get("model", "")
            cec = find_cec_inverter(item.get("manufacturer", ""), model)
            if cec is None:
                add(id=f"cec.missing.{model}", severity="error",
                    title=f"{item.get('manufacturer')} {model} is not on the CEC approved list",
                    clause="AS/NZS 4777.2; CEC approved inverter list", params=[key],
                    detail="The device was not found in the (synchronised) CEC list; the DNSP will not approve it.",
                    suggestion="Replace it with a CEC-listed model, or check the model name.")
                continue
            if date.fromisoformat(cec["expires"]) < today:
                add(id=f"cec.expired.{model}", severity="error", title=f"{model} CEC listing has expired",
                    clause="CEC approved inverter list", params=[key], detail=f"Listing valid until {cec['expires']}.",
                    suggestion="Choose a model with a current listing.")
            rated = item.get("rated_ac_kva", item.get("pcs_kva"))
            if rated is not None and abs(float(rated) - float(cec["rated_ac_kva"])) > 0.01:
                add(id=f"cec.rating.{model}", severity="error", title=f"{model} rating does not match the CEC listing",
                    clause="Equipment list ↔ CEC listing consistency", params=[key],
                    detail=f"Entered {rated} kVA; CEC lists {cec['rated_ac_kva']} kVA.",
                    suggestion="Correct the equipment list to the CEC value; the SLD will be marked stale automatically.")
            if not cec.get("as4777_2020"):
                add(id=f"cec.4777.{model}", severity="error", title=f"{model} is not certified to AS/NZS 4777.2:2020",
                    clause="AS/NZS 4777.2:2020", params=[key], detail="The CEC list shows a pre-2020 certification.",
                    suggestion="Choose a model certified to AS/NZS 4777.2:2020.")

    pack_id = p.get("rules.dnsp_pack")
    if pack_id:
        pack = load_pack(pack_id)
        req_region = pack["inverter_region"]
        if req_region is None:
            add(id="4777.region_unsourced", severity="warning",
                title=f"{pack['dnsp']} inverter region requirement not yet sourced",
                clause=f"{pack.ref}#inverter_region", params=["inverter.region"],
                detail="The rule pack has no sourced AS/NZS 4777.2 region setting for this DNSP.",
                suggestion="Obtain the DNSP technical standard and record the required region setting.")
        elif p.get("inverter.region") and p.get("inverter.region") != req_region:
            add(id="4777.region", severity="error", title="Inverter region setting does not match DNSP requirement",
                clause=f"{pack.ref}#inverter_region; AS/NZS 4777.2 Section 3", params=["inverter.region"],
                detail=f"Currently {p.get('inverter.region')}; {pack['dnsp']} requires {req_region}.",
                suggestion=f"Set all inverters to {req_region}.")
        if not pack.get("verified"):
            add(id="rules.unverified", severity="warning", title=f"{pack['dnsp']} rule pack not yet verified",
                clause=pack.ref, params=["rules.dnsp_pack"],
                detail="Rule pack values are placeholders and have not been checked against the DNSP's current technical standard.",
                suggestion="Have the rule maintainer verify and publish a verified version before formal submission.")

    # 4. Export limits
    scheme = p.get("export.scheme")
    if scheme == "requires_dnsp_assessment":
        max_ns = p.get("rules.export_max_without_study_kw")
        add(id="export.assessment", severity="warning",
            title="Requested export needs DNSP assessment",
            clause=p.params["rules.export_max_without_study_kw"].source.ref if "rules.export_max_without_study_kw" in p.params else "DNSP export rules",
            params=["export.requested_kw", "calc.inverter_ac_kva", "rules.export_max_without_study_kw"],
            detail=(f"Requested {p.get('export.requested_kw')} kW is outside the DNSP's standard export option "
                    f"({max_ns} kW up to {p.get('rules.export_static_option_max_kva')} kVA)." if max_ns is not None
                    else "The DNSP's standard export option is not yet sourced in the rule pack."),
            suggestion="Allow time and cost for a DNSP (paid) assessment, or reduce the export request; consider a battery to absorb surplus.")
    if p.get("calc.export_limiting_required") and not p.get("design.export_limiter"):
        add(id="export.device", severity="error", title="Export limiting device required",
            clause="DNSP export limit requirements; AS/NZS 4777.1 export control",
            params=["calc.export_limiting_required", "design.export_limiter"],
            detail=f"Generation capacity {kva} kVA exceeds the requested export of {p.get('export.requested_kw')} kW; "
                   "export control is required at the point of connection.",
            suggestion=f"Enter design.export_limiter (controller model, CT location); "
                       f"response time ≤ {p.get('rules.export_control_response_s', '?')} s.")

    # 5. Protection
    if p.get("calc.central_protection_required") is None and p.get("rules.dnsp_pack"):
        add(id="prot.threshold_unsourced", severity="warning", title="Central/interface protection threshold not yet sourced",
            clause=p.params["rules.central_protection_above_kva"].source.ref if "rules.central_protection_above_kva" in p.params else "DNSP rules",
            params=["rules.central_protection_above_kva"],
            detail="The rule pack does not yet state above which aggregate inverter kVA central protection is required.",
            suggestion="An engineer must determine the requirement from the DNSP technical standard.")
    if p.get("calc.central_protection_required") and not p.get("design.central_protection_relay"):
        add(id="prot.central", severity="error", title="Central protection relay required",
            clause=f"{p.params['rules.central_protection_above_kva'].source.ref}",
            params=["calc.central_protection_required", "design.central_protection_relay"],
            detail=f"Total capacity {kva} kVA exceeds the {p.get('rules.central_protection_above_kva')} kVA threshold.",
            suggestion="Enter the relay model in design.central_protection_relay; settings are in the protection settings schedule.")

    # 5b. DNSP rule pack (declarative rules with cited sources)
    ev = evaluate_project(p)
    if p.get("site.dnsp") and ev.status != "preliminary_only":
        add(id="rules.no_pack", severity="warning", title=f"No executable rule pack for {p.get('site.dnsp')}",
            clause=f"rule engine status: {ev.status}", params=["site.dnsp"],
            detail="No sourced rules exist for this DNSP yet, so pathway and protection triggers were not evaluated.",
            suggestion="Build the DNSP rule pack from official sources (see docs/rule-research-backlog.md).")
    if ev.status == "preliminary_only" and not ev.fired:
        add(id="rules.coverage_gap", severity="warning", title=f"No {p.get('site.dnsp')} rules cover this project yet",
            clause=f"rule pack {ev.pack}", params=["site.dnsp", "calc.connection_phase"],
            detail="The DNSP rule pack exists but none of its sourced rules apply to this connection type (e.g. QLD LV: STNW1174 not yet read).",
            suggestion="Extend the rule pack for this connection type before relying on the compliance result.")
    for r in ev.fired:
        urls = " ".join(d["url"] for d in r.source_docs)
        add(id=r.id, severity=r.severity, title=f"{r.id}: {r.outcome}",
            clause=f"{r.citation} {urls}".strip(), params=[FIELD_MAP.get(x, x) for x in r.fields],
            detail=f"Triggered by: {r.trigger}.",
            suggestion=f"Action: {r.action}. Engineering review: {r.engineering_review}."
                       + (f" Flag: {r.flag}." if r.flag else "")
                       + (f" Effective from {r.effective_from}." if r.effective_from else "")
                       + (f" Note: {r.notes}" if r.notes else ""))

    # 6. Design sanity
    ratio = p.get("calc.dc_ac_ratio")
    if ratio is not None and float(ratio) > 1.5:
        add(id="design.dcac", severity="warning", title=f"DC/AC ratio of {ratio} is high",
            clause="Design practice (≤1.33–1.5)", params=["pv.dc_kwp", "equipment.pv_inverters"],
            detail="Excessive oversizing causes significant clipping losses and may exceed inverter DC input limits.",
            suggestion="Add inverter capacity or reduce module count, and check the inverter datasheet DC limit.")
    if path == "MV" or p.get("design.topology") == "mv_kiosk":
        tx = p.get("connection.transformer_kva")
        if tx is None:
            add(id="mv.tx", severity="error", title="MV project is missing the kiosk transformer rating",
                clause="DNSP MV connection requirements", params=["connection.transformer_kva"],
                detail="The SLD and protection settings need the transformer rating.",
                suggestion="Enter connection.transformer_kva.")
        elif kva is not None and float(tx) < float(kva):
            add(id="mv.tx_small", severity="error", title="Transformer rating is below total inverter capacity",
                clause="Equipment rating coordination", params=["connection.transformer_kva", "calc.inverter_ac_kva"],
                detail=f"Transformer {tx} kVA < inverters {kva} kVA.",
                suggestion="Increase the transformer rating or limit inverter output.")

    # 7. Battery
    if p.get("equipment.bess"):
        add(id="bess.5139", severity="info", title="Battery installation must comply with AS/NZS 5139",
            clause="AS/NZS 5139:2019", params=["equipment.bess"],
            detail="Battery location, fire clearances, ventilation and signage must meet AS/NZS 5139.",
            suggestion="Show battery location and clearances on the site plan and verify on site.")

    # 8. Contractor licence
    exp = p.get("contractor.licence_expiry")
    try:
        expired = bool(exp) and date.fromisoformat(str(exp)) < today
    except ValueError:
        expired = False
        add(id="contractor.invalid_expiry", severity="error", title="Contractor licence expiry date is invalid",
            clause="State electrical safety legislation", params=["contractor.licence_expiry"],
            detail=f"Invalid date: {exp}", suggestion="Enter a valid date in YYYY-MM-DD format.")
    if expired:
        add(id="contractor.expired", severity="error", title="Electrical contractor licence has expired",
            clause="State electrical safety legislation", params=["contractor.licence_expiry"],
            detail=f"Valid until {exp}.", suggestion="Update the licence details.")

    # 9. Unconfirmed assumptions
    pending = p.assumptions()
    if pending:
        add(id="assumptions.pending", severity="warning", title=f"{len(pending)} assumption(s) awaiting engineer confirmation",
            clause="GridEasy data governance: unsourced or unconfirmed values cannot enter final documents",
            params=[x.key for x in pending],
            detail="AI-extracted or default values: " + ", ".join(f"{x.key}={x.value}" for x in pending),
            suggestion="Check each value and confirm it; all must be confirmed before the final package.")

    # 10. Document consistency
    stale = p.stale_documents()
    if stale:
        add(id="docs.stale", severity="error", title=f"{len(stale)} document(s) reference changed parameters",
            clause="Single source of truth consistency", params=[], detail="Stale: " + ", ".join(stale),
            suggestion="Regenerate these documents and sign them off again.")
    rank = {"error": 0, "warning": 1, "info": 2}
    return sorted(f, key=lambda x: rank[x.severity])
