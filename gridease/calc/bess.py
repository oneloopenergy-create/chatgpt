"""Battery sizing and economics: recommend a BESS size from load profile, tariff and export limit, with payback.

Simplified model (hourly, typical day × 365):
- PV output = kWp × daily yield × normalised daily shape;
- PV serves site load first, surplus charges the battery, then exports up to the limit; the rest is curtailed;
- the battery discharges to serve load in the peak window and overnight; no grid charging (conservative).
All defaults (yield, unit capex, round-trip efficiency) are written as assumptions for engineer confirmation.
"""
from __future__ import annotations

import math
from typing import Any

from ..core.model import Project, Source, SourceKind

DEFAULTS: dict[str, tuple[Any, str | None, str]] = {
    "pv.yield_kwh_per_kwp_day": (4.2, "kWh/kWp/day", "Rough annual-average daily yield for Sydney"),
    "bess.capex_per_kwh": (650.0, "AUD/kWh", "Rough installed C&I battery cost"),
    "bess.round_trip_eff": (0.88, None, "AC round-trip efficiency"),
    "bess.c_rate": (0.5, "1/h", "Power-to-energy ratio"),
    "tariff.peak_hours": ([15, 16, 17, 18, 19, 20], "h", "Peak window (local hours)"),
}


def pv_shape() -> list[float]:
    """Normalised daily PV shape (sine from 06:00 to 18:00), sums to 1."""
    raw = [max(0.0, math.sin(math.pi * (h + 0.5 - 6) / 12)) if 6 <= h < 18 else 0.0 for h in range(24)]
    s = sum(raw)
    return [r / s for r in raw]


def ensure_defaults(p: Project) -> None:
    for k, (v, unit, note) in DEFAULTS.items():
        if p.get(k) is None:
            p.set_param(k, v, Source(kind=SourceKind.ASSUMPTION, ref=f"default:{k}", note=note), unit=unit)


def simulate_day(load: list[float], pv: list[float], export_limit: float, e_kwh: float, p_kw: float,
                 eff: float, peak: set[int]) -> dict[str, float]:
    soc = 0.0
    imp_peak = imp_off = exp = curtail = 0.0
    sqrt_eff = math.sqrt(eff)
    for _ in range(2):  # first pass warms up SOC; keep the second pass
        imp_peak = imp_off = exp = curtail = 0.0
        for h in range(24):
            net = pv[h] - load[h]
            if net >= 0:
                ch = min(net, p_kw, (e_kwh - soc) / sqrt_eff if e_kwh else 0.0)
                soc += ch * sqrt_eff
                surplus = net - ch
                e = min(surplus, export_limit)
                exp += e
                curtail += surplus - e
            else:
                deficit = -net
                dis = 0.0
                if h in peak or h >= 18 or h < 6:
                    dis = min(deficit, p_kw, soc * sqrt_eff)
                    soc -= dis / sqrt_eff if sqrt_eff else 0.0
                grid = deficit - dis
                if h in peak:
                    imp_peak += grid
                else:
                    imp_off += grid
    return {"import_peak": imp_peak, "import_offpeak": imp_off, "export": exp, "curtail": curtail}


def size_bess(p: Project, sizes_kwh: list[float] | None = None) -> dict[str, Any]:
    from ..core.validation import validate_parameter
    for key in ("load.profile_kw", "bess.round_trip_eff", "bess.capex_per_kwh", "bess.c_rate",
                "pv.yield_kwh_per_kwp_day", "tariff.peak_hours"):
        if p.get(key) is not None:
            validate_parameter(key, p.get(key))
    required = ("pv.dc_kwp", "export.requested_kw", "tariff.import_peak_c_per_kwh",
                "tariff.import_offpeak_c_per_kwh", "tariff.export_c_per_kwh")
    missing = [key for key in required if p.get(key) is None]
    if missing:
        raise ValueError("Battery economics needs: " + ", ".join(missing))
    ensure_defaults(p)
    load = p.get("load.profile_kw")
    if not load or len(load) != 24:
        raise ValueError("A 24-point typical-day load profile load.profile_kw (kW) is required")
    kwp = float(p.get("pv.dc_kwp") or 0)
    yield_ = float(p.get("pv.yield_kwh_per_kwp_day"))
    pv = [kwp * yield_ * s for s in pv_shape()]
    export_limit = float(p.get("export.requested_kw") or 0)
    t_peak = float(p.get("tariff.import_peak_c_per_kwh") or 0) / 100
    t_off = float(p.get("tariff.import_offpeak_c_per_kwh") or 0) / 100
    t_exp = float(p.get("tariff.export_c_per_kwh") or 0) / 100
    capex_kwh = float(p.get("bess.capex_per_kwh"))
    eff = float(p.get("bess.round_trip_eff"))
    c_rate = float(p.get("bess.c_rate"))
    peak = set(p.get("tariff.peak_hours"))

    def annual_cost(e: float) -> tuple[float, dict[str, float]]:
        d = simulate_day(load, pv, export_limit, e, e * c_rate, eff, peak)
        cost = 365 * (d["import_peak"] * t_peak + d["import_offpeak"] * t_off - d["export"] * t_exp)
        return cost, d

    base_cost, base = annual_cost(0.0)
    if sizes_kwh is None:
        daily_load = sum(load)
        top = max(50.0, round(daily_load * 0.6 / 50) * 50)
        step = max(50, math.ceil(top / 200 / 50) * 50)
        sizes_kwh = list(range(step, int(top) + 1, step)) or [50]
    rows = []
    for e in sizes_kwh:
        cost, d = annual_cost(float(e))
        saving = base_cost - cost
        capex = e * capex_kwh
        payback = capex / saving if saving > 0 else None
        rows.append({"energy_kwh": e, "power_kw": round(e * c_rate, 1), "capex_aud": round(capex),
                     "annual_saving_aud": round(saving), "payback_years": round(payback, 1) if payback else None,
                     "curtail_kwh_day": round(d["curtail"], 1)})
    viable = [r for r in rows if r["payback_years"] is not None]
    best = min(viable, key=lambda r: (r["payback_years"], -r["energy_kwh"])) if viable else None
    used = ["load.profile_kw", "pv.dc_kwp", "pv.yield_kwh_per_kwp_day", "export.requested_kw",
            "tariff.import_peak_c_per_kwh", "tariff.import_offpeak_c_per_kwh", "tariff.export_c_per_kwh",
            "bess.capex_per_kwh", "bess.round_trip_eff", "bess.c_rate", "tariff.peak_hours"]
    src = Source(kind=SourceKind.CALCULATION,
                 ref="calc:size_bess(" + ",".join(f"{k}@v{p.params[k].version}" for k in used if k in p.params) + ")")
    if not best:
        for key in ("calc.bess_recommended_kwh", "calc.bess_payback_years"):
            p.remove_param(key)
    if best:
        p.set_param("calc.bess_recommended_kwh", best["energy_kwh"], src, unit="kWh", needs_confirmation=False)
        p.set_param("calc.bess_payback_years", best["payback_years"], src, unit="years", needs_confirmation=False)
    return {"baseline": {"annual_cost_aud": round(base_cost), "curtail_kwh_day": round(base["curtail"], 1)},
            "options": rows, "recommended": best, "inputs": used}
