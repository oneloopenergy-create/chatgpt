"""Smart intake: extract fields from a free-text project brief, keeping the evidence for each value.

The current implementation is a deterministic rule extractor (regex + CEC model matching), the baseline and
fallback for a future LLM extractor. Any LLM extractor must implement the same interface, run onshore in
Australia (no data leaves the country), and its output is always marked for engineer confirmation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..core.model import Project, Source, SourceKind
from ..rules.library import DNSP_IDS, load_pack


@dataclass
class Extracted:
    key: str
    value: Any
    unit: str | None
    evidence: str  # source text snippet


@dataclass
class ExtractionResult:
    fields: list[Extracted] = field(default_factory=list)

    def add(self, key: str, value: Any, unit: str | None, evidence: str) -> None:
        self.fields.append(Extracted(key, value, unit, evidence.strip()))


class Extractor(Protocol):
    def extract(self, text: str) -> ExtractionResult: ...


_NUM = r"(\d+(?:[.,]\d+)?)"


def _f(s: str) -> float:
    v = float(s.replace(",", ""))
    return int(v) if v.is_integer() else v


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


class RuleExtractor:
    def extract(self, text: str) -> ExtractionResult:
        r = ExtractionResult()
        low = text.lower()

        for name in sorted(DNSP_IDS, key=len, reverse=True):
            if name in low:
                pack = load_pack(DNSP_IDS[name])
                r.add("site.dnsp", pack["dnsp"], None, name)
                r.add("site.state", pack["state"], None, name)
                break

        if m := re.search(r"NMI[\s:#]*([0-9A-Z]{10,11})", text, re.I):
            r.add("site.nmi", m.group(1).upper(), None, m.group(0))
        if m := re.search(_NUM + r"\s*kWp", text, re.I):
            r.add("pv.dc_kwp", _f(m.group(1)), "kWp", m.group(0))
        if m := re.search(r"max(?:imum)? demand[^\d]{0,8}" + _NUM + r"\s*kVA", text, re.I):
            r.add("connection.max_demand_kva", _f(m.group(1)), "kVA", m.group(0))
        if m := re.search(r"export[^\d]{0,12}" + _NUM + r"\s*kW(?!h)", text, re.I):
            r.add("export.requested_kw", _f(m.group(1)), "kW", m.group(0))
        elif m := re.search(r"zero[- ]export", text, re.I):
            r.add("export.requested_kw", 0, "kW", m.group(0))
        if m := re.search(r"(11|22|33)\s*kV", text, re.I):
            r.add("connection.supply_voltage_v", int(m.group(1)) * 1000, "V", m.group(0))
        elif m := re.search(r"low[- ]voltage|400\s*V\b|\bLV\b", text, re.I):
            r.add("connection.supply_voltage_v", 400, "V", m.group(0))
        if m := re.search(r"(?:kiosk|transformer)[^\d]{0,6}" + _NUM + r"\s*kVA", text, re.I):
            r.add("connection.transformer_kva", _f(m.group(1)), "kVA", m.group(0))
        # kW, kVA and kWh are kept distinct (Ausgrid rule pack AG-R010)
        if m := re.search(r"(?:max(?:imum)?\s+)?generation[^\d]{0,12}" + _NUM + r"\s*kW(?!h)", text, re.I):
            r.add("generation.max_kw", _f(m.group(1)), "kW", m.group(0))
        if m := re.search(r"(?:AEMO\s+)?registration[^.;,]{0,20}?\b(registered|exempt|pending|unknown)\b"
                          r"|\b(exempt|registered)\s+(?:from\s+)?(?:AEMO\s+)?registration", text, re.I):
            r.add("registration.aemo_status", (m.group(1) or m.group(2)).lower(), None, m.group(0))
        if m := re.search(r"\bno existing (?:solar|generation|embedded generation|EG|PV)\b", text, re.I):
            r.add("site.existing_eg_present", False, None, m.group(0))
        elif m := re.search(r"\bexisting (?:solar|generation|embedded generation|EG|PV)\b(?:[^\d.;]{0,12}" + _NUM + r"\s*kVA)?", text, re.I):
            r.add("site.existing_eg_present", True, None, m.group(0))
            if m.group(1):
                r.add("site.existing_eg_kva", _f(m.group(1)), "kVA", m.group(0))
        for key, pat in (("project.commissioning_date", r"commission(?:ed|ing)?(?:\s+date)?[^\d]{0,12}(\d{4}-\d{2}-\d{2})"),
                         ("project.connection_agreement_date", r"connection agreement(?:\s+signed)?[^\d]{0,12}(\d{4}-\d{2}-\d{2})"),
                         ("project.dnsp_approval_date", r"approv(?:ed|al)(?:\s+date)?[^\d]{0,12}(\d{4}-\d{2}-\d{2})")):
            if m := re.search(pat, text, re.I):
                r.add(key, m.group(1), None, m.group(0))
        if m := re.search(r"\bclass\s+(A1|A2|B)\b", text, re.I):
            r.add("connection.eg_class", m.group(1).upper(), None, m.group(0))
        if m := re.search(r"\bSCR\s*(?:of|=|:)?\s*" + _NUM, text, re.I):
            r.add("connection.scr", _f(m.group(1)), None, m.group(0))
        if m := re.search(r"\b(?:NSW|QLD)\s+(\d{4})\b", text):
            r.add("site.postcode", m.group(1), None, m.group(0))
        if m := re.search(r"\bABN[\s:#]*((?:\d\s?){11})", text, re.I):
            r.add("site.applicant_abn", re.sub(r"\s", "", m.group(1)), None, m.group(0))
        if m := re.search(r"charg(?:e|ing)[^\d]{0,10}" + _NUM + r"\s*kW(?!h)", text, re.I):
            r.add("bess.charge_kw", _f(m.group(1)), "kW", m.group(0))
        if m := re.search(r"discharg(?:e|ing)[^\d]{0,10}" + _NUM + r"\s*kW(?!h)", text, re.I):
            r.add("bess.discharge_kw", _f(m.group(1)), "kW", m.group(0))

        # Equipment: find CEC-listed models in the text and read the quantity before each
        pv_inv, bess_pcs = [], []
        compact = _norm(text)
        for inv in load_pack("cec_inverters")["inverters"]:
            if _norm(inv["model"]) not in compact:
                continue
            pat = r"(\d+)\s*(?:x|×|\*)?\s*(?:" + re.escape(inv["manufacturer"]) + r"\s*)?" + \
                  r"[\s\-]*".join(map(re.escape, re.split(r"[\s\-]+", inv["model"])))
            m = re.search(pat, text, re.I)
            qty = int(m.group(1)) if m else 1
            ev = m.group(0) if m else inv["model"]
            item = {"manufacturer": inv["manufacturer"], "model": inv["model"], "qty": qty}
            if inv.get("kind") == "bess_pcs":
                bess_pcs.append((item | {"pcs_kva": inv["rated_ac_kva"]}, ev))
            else:
                pv_inv.append((item | {"rated_ac_kva": inv["rated_ac_kva"]}, ev))
        if pv_inv:
            r.add("equipment.pv_inverters", [i for i, _ in pv_inv], None, "; ".join(e for _, e in pv_inv))
        m_kwh = re.search(_NUM + r"\s*kWh", text, re.I)
        if bess_pcs:
            items = [i for i, _ in bess_pcs]
            if m_kwh:
                total = _f(m_kwh.group(1))
                n = sum(i["qty"] for i in items)
                if n <= 0:
                    raise ValueError("Battery quantity must be greater than zero")
                for i in items:
                    i["energy_kwh"] = round(total / n, 1)
            r.add("equipment.bess", items, None, "; ".join(e for _, e in bess_pcs) + (f"; {m_kwh.group(0)}" if m_kwh else ""))

        if m := re.search(r"kiosk|(?:11|22|33)\s*kV", text, re.I):
            topo, ev = "mv_kiosk", m.group(0)
        elif m := (re.search(r"battery|BESS|storage", text, re.I) or m_kwh):
            topo, ev = "pv_bess_ac_coupled", m.group(0)
        elif bess_pcs:
            topo, ev = "pv_bess_ac_coupled", "BESS PCS model"
        elif m := re.search(r"ground[- ]mount(?:ed)?", text, re.I):
            topo, ev = "ground_pv", m.group(0)
        else:
            topo, ev = "rooftop_pv", "default: rooftop PV"
        r.add("design.topology", topo, None, ev)
        return r


def apply_extraction(p: Project, res: ExtractionResult, source_ref: str = "brief", actor: str = "ai-intake") -> list[str]:
    """Write into the source of truth; never overwrites user-entered or engineer-confirmed parameters."""
    written = []
    for e in res.fields:
        cur = p.params.get(e.key)
        if cur is not None and (cur.source.kind == SourceKind.USER_INPUT or cur.confirmed_by):
            continue
        p.set_param(e.key, e.value, Source(kind=SourceKind.BRIEF, ref=source_ref, note=f"Evidence: {e.evidence}"),
                    unit=e.unit, actor=actor)
        written.append(e.key)
    return written
