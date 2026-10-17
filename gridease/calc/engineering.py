"""Deterministic engineering calculations.

AI never produces numbers: this module reads parameters from the project source of truth and writes
results back as ``calc.*`` with source ``calc:<function>(inputs@versions)`` for full traceability.
"""
from __future__ import annotations

import math
from typing import Any

from ..core.model import Project, Source, SourceKind
from ..rules.library import dnsp_pack, load_pack

# Inverter fault-current multiplier: conservative assumption when no OEM data; engineer must confirm
DEFAULT_INVERTER_FAULT_MULTIPLIER = 1.2


class MissingInput(ValueError):
    def __init__(self, keys: list[str]):
        super().__init__(f"Missing input parameters: {', '.join(keys)}")
        self.keys = keys


def _require(p: Project, *keys: str) -> None:
    missing = [k for k in keys if p.get(k) is None]
    if missing:
        raise MissingInput(missing)


def _calc_source(p: Project, fn: str, inputs: list[str], note: str | None = None) -> Source:
    used = ",".join(f"{k}@v{p.params[k].version}" for k in inputs if k in p.params)
    return Source(kind=SourceKind.CALCULATION, ref=f"calc:{fn}({used})", note=note)


def _put(p: Project, key: str, value: Any, unit: str | None, fn: str, inputs: list[str], note: str | None = None):
    p.set_param(key, value, _calc_source(p, fn, inputs, note), unit=unit, needs_confirmation=False)


def apply_dnsp_rules(p: Project) -> None:
    """Step 2, rule matching: write the applicable DNSP / 4777.2 rule values into the source of truth."""
    _require(p, "site.dnsp")
    pack = dnsp_pack(p.get("site.dnsp"))
    region, ref = pack.at("inverter_region")
    p.set_param("rules.dnsp_pack", pack["id"], Source(kind=SourceKind.RULE, ref=pack.ref), needs_confirmation=False)
    current_region = p.params.get("inverter.region")
    if current_region is None or current_region.source.kind == SourceKind.RULE:
        p.set_param("inverter.region", region, Source(kind=SourceKind.RULE, ref=ref, note=pack.get("inverter_region_source")),
                    needs_confirmation=False)
    # null in the pack = not yet sourced; written as None so downstream logic reports it as unknown
    for path, key, unit in [
        ("central_protection.required_above_kva", "rules.central_protection_above_kva", "kVA"),
        ("export.max_negotiated_without_study_kw", "rules.export_max_without_study_kw", "kW"),
        ("export.static_option_max_kva", "rules.export_static_option_max_kva", "kVA"),
        ("export.dynamic_supported", "rules.dynamic_export_supported", None),
        ("export.export_control_response_s", "rules.export_control_response_s", "s"),
        ("connection.lv_max_kva", "rules.lv_max_kva", "kVA"),
    ]:
        try:
            v, r = pack.at(path)
        except KeyError:
            v, r = None, f"{pack.ref}#{path}"
        p.set_param(key, v, Source(kind=SourceKind.RULE, ref=r, note=None if v is not None else "not yet sourced"),
                    unit=unit, needs_confirmation=False)


def capacity_summary(p: Project) -> None:
    if p.get("equipment.pv_inverters") is None and p.get("equipment.bess") is None:
        raise MissingInput(["equipment.pv_inverters or equipment.bess"])
    pv_inv = p.get("equipment.pv_inverters") or []
    bess = p.get("equipment.bess") or []
    pv_kva = sum(float(i["rated_ac_kva"]) * int(i.get("qty", 1)) for i in pv_inv)
    pcs_kva = sum(float(b["pcs_kva"]) * int(b.get("qty", 1)) for b in bess)
    energy = (sum(float(b["energy_kwh"]) * int(b.get("qty", 1)) for b in bess)
              if all(b.get("energy_kwh") is not None for b in bess) else None)
    ins = ["equipment.pv_inverters", "equipment.bess"]
    _put(p, "calc.pv_inverter_ac_kva", round(pv_kva, 2), "kVA", "capacity_summary", ins)
    _put(p, "calc.bess_pcs_kva", round(pcs_kva, 2), "kVA", "capacity_summary", ins)
    _put(p, "calc.bess_energy_kwh", round(energy, 2) if energy is not None else None, "kWh", "capacity_summary", ins)
    _put(p, "calc.inverter_ac_kva", round(pv_kva + pcs_kva, 2), "kVA", "capacity_summary", ins,
         note="Sum of PV inverter and BESS PCS nameplate AC ratings")
    if not p.get("pv.dc_kwp") or not pv_kva:
        p.remove_param("calc.dc_ac_ratio")
    if p.get("pv.dc_kwp") and pv_kva:
        _put(p, "calc.dc_ac_ratio", round(float(p.get("pv.dc_kwp")) / pv_kva, 3), None, "capacity_summary",
             ["pv.dc_kwp", *ins])


def connection_path(p: Project) -> None:
    _require(p, "calc.inverter_ac_kva", "connection.supply_voltage_v")
    ena = load_pack("ena_der")
    kva = float(p.get("calc.inverter_ac_kva"))
    v = float(p.get("connection.supply_voltage_v"))
    if kva <= ena["categories"]["small_max_kva"]:
        path = "small_out_of_scope"
    elif kva > ena["categories"]["mv_nem_max_kva"]:
        path = "path_b_nem_registered"
    elif v >= 1000:
        path = "MV"
    else:
        path = "LV"
    _put(p, "calc.connection_path", path, None, "connection_path",
         ["calc.inverter_ac_kva", "connection.supply_voltage_v"])
    _put(p, "calc.connection_voltage_kv", round(v / 1000, 3), "kV", "connection_path", ["connection.supply_voltage_v"])
    _put(p, "calc.connection_phase", "HV" if v >= 1000 else "LV", None, "connection_path",
         ["connection.supply_voltage_v"], note="Nominal voltage only; DNSP HV classification must be validated")
    # Protection trigger uses aggregate inverter kVA (not generation kW); None = DNSP threshold not yet sourced
    thr = p.get("rules.central_protection_above_kva")
    _put(p, "calc.central_protection_required", kva > float(thr) if thr is not None else None, None,
         "connection_path", ["calc.inverter_ac_kva", "rules.central_protection_above_kva"])


def rated_and_fault_current(p: Project) -> None:
    _require(p, "calc.inverter_ac_kva", "connection.supply_voltage_v")
    if p.get("inverter.fault_multiplier") is None:
        p.set_param("inverter.fault_multiplier", DEFAULT_INVERTER_FAULT_MULTIPLIER,
                    Source(kind=SourceKind.ASSUMPTION, ref="default:inverter_fault_multiplier",
                           note="Conservative assumption when OEM fault-current data is not provided"))
    kva = float(p.get("calc.inverter_ac_kva"))
    v = float(p.get("connection.supply_voltage_v"))
    i_rated = kva * 1000 / (math.sqrt(3) * v)
    ins = ["calc.inverter_ac_kva", "connection.supply_voltage_v"]
    _put(p, "calc.rated_current_a", round(i_rated, 1), "A", "rated_and_fault_current", ins)
    _put(p, "calc.fault_contribution_a", round(i_rated * float(p.get("inverter.fault_multiplier")), 1), "A",
         "rated_and_fault_current", [*ins, "inverter.fault_multiplier"])


def export_scheme(p: Project) -> None:
    """Export limit scheme and whether an export limiting device is needed.

    static = within the DNSP's standard export option; requires_dnsp_assessment = above it, or the DNSP's
    option is not yet sourced (e.g. Ausgrid: 30 kW option for >30–200 kVA, paid assessment otherwise).
    """
    _require(p, "export.requested_kw", "calc.inverter_ac_kva")
    req = float(p.get("export.requested_kw"))
    gen = float(p.get("calc.inverter_ac_kva"))  # kVA ≈ kW (PF = 1), conservative
    max_ns = p.get("rules.export_max_without_study_kw")
    cap = p.get("rules.export_static_option_max_kva")
    ins = ["export.requested_kw", "calc.inverter_ac_kva", "rules.export_max_without_study_kw",
           "rules.export_static_option_max_kva", "rules.dynamic_export_supported"]
    if req <= 0:
        scheme = "zero_export"
    elif max_ns is not None and req <= float(max_ns) and (cap is None or gen <= float(cap)):
        scheme = "static"
    elif p.get("rules.dynamic_export_supported"):
        scheme = "dynamic"
    else:
        scheme = "requires_dnsp_assessment"
    if p.get("export.scheme") is None or p.params["export.scheme"].source.kind == SourceKind.CALCULATION:
        _put(p, "export.scheme", scheme, None, "export_scheme", ins)
    _put(p, "calc.export_limiting_required", gen > req, None, "export_scheme",
         ["export.requested_kw", "calc.inverter_ac_kva"])
    _put(p, "calc.curtailable_kw", round(max(gen - req, 0.0), 1), "kW", "export_scheme",
         ["export.requested_kw", "calc.inverter_ac_kva"])


def protection_settings(p: Project) -> list[dict[str, Any]]:
    """Protection settings: inverter-integrated (4777.2) + central protection (DNSP). Rows carry their source."""
    _require(p, "rules.dnsp_pack", "inverter.region", "calc.connection_path")
    pack = load_pack(p.get("rules.dnsp_pack"))
    std = load_pack("as_nzs_4777_2")
    rows: list[dict[str, Any]] = []
    for r in std["passive_protection"]:
        rows.append({"location": "Inverter (integrated)", **r, "source": f"{std.ref}#passive_protection"})
    if p.get("calc.central_protection_required"):
        mv = p.get("calc.connection_path") == "MV"
        for r in pack["central_protection"]["settings"]:
            if r.get("mv_only") and not mv:
                continue
            row = {k: v for k, v in r.items() if k != "mv_only"}
            rows.append({"location": "Central protection relay (point of connection)", **row,
                         "source": f"{pack.ref}#central_protection.settings"})
    return rows


def site_postcode(p: Project) -> None:
    """Derive the postcode from the site address when not entered (needed for postcode-staged rules)."""
    import re
    addr = p.get("site.address")
    cur = p.params.get("site.postcode")
    if not addr or (cur is not None and cur.source.kind != SourceKind.CALCULATION):
        return
    m = re.search(r"\b(?:NSW|QLD|VIC|SA|TAS|ACT|NT|WA)\s+(\d{4})\b", str(addr))
    if m:
        _put(p, "site.postcode", m.group(1), None, "site_postcode", ["site.address"])
    elif cur is not None and cur.source.kind == SourceKind.CALCULATION:
        p.remove_param("site.postcode")


def run_all(p: Project) -> list[str]:
    """Run all calculations in dependency order. Returns notes for steps skipped due to missing inputs."""
    skipped = []
    for fn in (apply_dnsp_rules, site_postcode, capacity_summary, connection_path, rated_and_fault_current, export_scheme):
        try:
            fn(p)
        except (ValueError, KeyError, TypeError, ZeroDivisionError) as e:
            skipped.append(f"{fn.__name__}: {e}")
            if fn is apply_dnsp_rules:
                for key, prm in list(p.params.items()):
                    if prm.source.kind == SourceKind.RULE:
                        p.remove_param(key)
            # Remove obsolete outputs rather than reuse calculations whose inputs failed.
            for key, prm in list(p.params.items()):
                if prm.source.kind == SourceKind.CALCULATION and prm.source.ref.startswith(f"calc:{fn.__name__}("):
                    p.remove_param(key)
    return skipped
