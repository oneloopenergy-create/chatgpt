"""Document generation: every document is generated from the source of truth and records the parameter versions used."""
from __future__ import annotations

import csv
import io
import json
from html import escape
from typing import Any, Callable

from ..calc.bess import size_bess
from ..calc.engineering import protection_settings
from ..core.model import Document, Project
from ..rules.library import find_cec_inverter, load_pack
from ..sld.generator import generate_sld

DRAFT_BANNER = "DRAFT — subject to review and sign-off by a registered engineer"


class _Tracker:
    def __init__(self, p: Project):
        self.p = p
        self.used: dict[str, int] = {}

    def __call__(self, key: str, default: Any = None) -> Any:
        prm = self.p.params.get(key)
        if prm is None:
            self.used[key] = 0
            return default
        self.used[key] = prm.version
        return prm.value


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, (list, dict)):
        return json.dumps(v)
    return str(v)


def application_form(p: Project) -> Document:
    g = _Tracker(p)
    pack = load_pack(g("rules.dnsp_pack"))
    rows, todo = [], []
    for fld in pack["application_form"]["fields"]:
        val = g(fld["param"])
        prm = p.params.get(fld["param"])
        src = prm.source.ref if prm else "—"
        flag = ""
        if val is None:
            todo.append(f"Application field missing: {fld['field']}")
            flag = "Missing"
        elif prm and prm.is_assumption:
            flag = "Unconfirmed"
        rows.append(f"<tr><td>{escape(fld['field'])}</td><td>{escape(_fmt(val))} {escape(prm.unit or '') if prm else ''}</td>"
                    f"<td class=src>{escape(src)}</td><td class=flag>{flag}</td></tr>")
    html = f"""<!doctype html><html lang=en><meta charset=utf-8><title>{escape(pack['application_form']['template'])}</title>
<style>body{{font-family:Arial,sans-serif;margin:24px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #bbb;padding:6px;font-size:13px;text-align:left}}
.src{{color:#666;font-size:11px}}.flag{{color:#b00;font-weight:bold}}.banner{{color:#b00;font-weight:bold}}</style>
<p class=banner>{DRAFT_BANNER}</p>
<h1>{escape(pack['application_form']['template'])}</h1>
<p>Project: {escape(p.name)} · Rule pack: {escape(pack.ref)}</p>
<table><tr><th>Field</th><th>Value</th><th>Source</th><th>Status</th></tr>{''.join(rows)}</table></html>"""
    return Document(doc_id="application_form", title="DNSP connection application", filename="01_application_form.html",
                    content=html, content_type="text/html", inputs=g.used, todo=todo)


def sld(p: Project) -> Document:
    svg, used, todo = generate_sld(p)
    return Document(doc_id="sld", title="Single line diagram", filename="02_single_line_diagram.svg", content=svg,
                    content_type="image/svg+xml", inputs=used, requires_signoff=True, todo=todo)


def protection(p: Project) -> Document:
    rows = protection_settings(p)
    used = {k: p.params[k].version for k in ("rules.dnsp_pack", "inverter.region", "calc.connection_path",
                                               "calc.central_protection_required") if k in p.params}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([DRAFT_BANNER])
    w.writerow(["Location", "Function", "ANSI", "Setting", "Trip time (s)", "Basis"])
    for r in rows:
        w.writerow([r["location"], r["function"], r["ansi"], r["setting"], r["trip_time_s"], r["source"]])
    todo = []
    if p.get("calc.central_protection_required") and not p.get("design.central_protection_relay"):
        todo.append("Central protection relay model TBC")
    return Document(doc_id="protection_settings", title="Protection scheme and settings", filename="03_protection_settings.csv",
                    content=buf.getvalue(), content_type="text/csv", inputs=used, requires_signoff=True, todo=todo)


def equipment_list(p: Project) -> Document:
    g = _Tracker(p)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Category", "Manufacturer", "Model", "Qty", "Rated AC (kVA)", "Energy (kWh)", "CEC listed",
                "CEC expiry", "AS/NZS 4777.2:2020"])
    for cat, key, rated in (("PV inverter", "equipment.pv_inverters", "rated_ac_kva"), ("BESS PCS", "equipment.bess", "pcs_kva")):
        for it in g(key, []) or []:
            cec = find_cec_inverter(it["manufacturer"], it["model"])
            w.writerow([cat, it["manufacturer"], it["model"], it.get("qty", 1), it.get(rated),
                        it.get("energy_kwh", ""), "Yes" if cec else "No", cec["expires"] if cec else "",
                        "Yes" if cec and cec.get("as4777_2020") else "No"])
    w.writerow([])
    w.writerow(["Inverter region setting", g("inverter.region")])
    w.writerow(["Total inverter AC capacity (kVA)", g("calc.inverter_ac_kva")])
    return Document(doc_id="equipment_list", title="Inverter and battery equipment list", filename="04_equipment_list.csv",
                    content=buf.getvalue(), content_type="text/csv", inputs=g.used)


def export_scheme_doc(p: Project) -> Document:
    g = _Tracker(p)
    names = {"zero_export": "Zero export", "static": "Static export limit", "dynamic": "Dynamic (flexible) exports",
             "requires_dnsp_assessment": "Requires DNSP assessment"}
    scheme = g("export.scheme")
    md = f"""> {DRAFT_BANNER}

# Export limit scheme — {p.name}

| Item | Value |
|---|---|
| DNSP | {_fmt(g('site.dnsp'))} |
| Total inverter AC capacity | {_fmt(g('calc.inverter_ac_kva'))} kVA |
| Requested export limit | {_fmt(g('export.requested_kw'))} kW |
| Scheme | {names.get(scheme, _fmt(scheme))} |
| Export limiting device required | {'Yes' if g('calc.export_limiting_required') else 'No'} |
| Maximum curtailment | {_fmt(g('calc.curtailable_kw'))} kW |
| Required export control response time | ≤ {_fmt(g('rules.export_control_response_s'))} s |
| Export limiting controller | {_fmt(g('design.export_limiter'))} |
| Battery | {_fmt(g('calc.bess_energy_kwh', 0))} kWh / PCS {_fmt(g('calc.bess_pcs_kva', 0))} kVA |

## Control philosophy
Three-phase CTs and an export limiting controller are installed at the point of connection (load side of the
revenue meter) to measure active power in real time. As export approaches the limit, the controller reduces
inverter active power over Modbus/SunSpec and prioritises battery charging. On loss of communications the
inverters must fall below the limit within the required time (fail-safe).
"""
    todo = [] if g("design.export_limiter") or not g("calc.export_limiting_required") else ["Export limiting controller model TBC"]
    return Document(doc_id="export_scheme", title="Export limit scheme", filename="05_export_limit_scheme.md",
                    content=md, content_type="text/markdown", inputs=g.used, todo=todo)


def site_plan(p: Project) -> Document:
    g = _Tracker(p)
    survey = g("site.survey_kmz")
    lat, lon = g("site.lat"), g("site.lon")
    todo = []
    if not survey:
        todo.append("No survey KMZ / cadastral data: the site plan may only be drawn from verified data; currently flagged unverified")
    md = f"""> {DRAFT_BANNER}

# Site plan (information checklist) — {p.name}

- Site address: {_fmt(g('site.address'))}
- Coordinates: {_fmt(lat)}, {_fmt(lon)} {'(unverified)' if not survey else ''}
- Survey / cadastral data: {_fmt(survey) if survey else '**Not provided — unverified data, do not draw from it**'}

To show: revenue meter and main switchboard, inverter locations, export limiting CTs, central protection,
battery (AS/NZS 5139 clearances), DNSP point of connection and isolation points, fire access.
"""
    return Document(doc_id="site_plan", title="Site plan", filename="06_site_plan.md", content=md,
                    content_type="text/markdown", inputs=g.used, todo=todo)


def bess_report(p: Project) -> Document:
    res = size_bess(p)
    used = {k: p.params[k].version for k in res["inputs"] if k in p.params}
    rec = res["recommended"]
    rows = "".join(
        f"<tr{' class=rec' if rec and o['energy_kwh'] == rec['energy_kwh'] else ''}><td>{o['energy_kwh']}</td><td>{o['power_kw']}</td>"
        f"<td>{o['capex_aud']:,}</td><td>{o['annual_saving_aud']:,}</td><td>{o['payback_years'] or '—'}</td>"
        f"<td>{o['curtail_kwh_day']}</td></tr>" for o in res["options"])
    assumptions = "".join(f"<li>{escape(k)} = {escape(_fmt(p.get(k)))} ({escape(p.params[k].source.note or p.params[k].source.ref)})"
                          f"{' <b>unconfirmed</b>' if p.params[k].is_assumption else ''}</li>"
                          for k in res["inputs"] if k in p.params and p.params[k].source.kind.value == "assumption")
    recommendation = (f"{rec['energy_kwh']} kWh / {rec['power_kw']} kW, payback about {rec['payback_years']} years"
                      if rec else "No economic payback at current tariffs")
    html = f"""<!doctype html><html lang=en><meta charset=utf-8><title>Battery sizing and payback — {escape(p.name)}</title>
<style>body{{font-family:Arial,sans-serif;margin:24px}}table{{border-collapse:collapse}}td,th{{border:1px solid #bbb;padding:6px 10px;text-align:right}}
.rec{{background:#e9f7ec;font-weight:bold}}</style>
<h1>Battery sizing and payback</h1><p>Project: {escape(p.name)}</p>
<p>Baseline without battery: net annual energy cost about AUD {res['baseline']['annual_cost_aud']:,}; curtailment {res['baseline']['curtail_kwh_day']} kWh/day.</p>
<p>Recommendation: <b>{recommendation}</b></p>
<table><tr><th>Energy kWh</th><th>Power kW</th><th>Capex AUD</th><th>Annual saving AUD</th><th>Payback years</th><th>Curtailment kWh/day</th></tr>{rows}</table>
<h3>Assumptions</h3><ul>{assumptions}</ul>
<p style="color:#666">Based on a typical-day load profile and a simplified PV curve; for option comparison only, not investment advice.</p></html>"""
    return Document(doc_id="bess_report", title="Battery sizing and payback report", filename="07_bess_economics.html",
                    content=html, content_type="text/html", inputs=used)


def change_log(p: Project) -> Document:
    lines = [f"# RFI and change log — {p.name}", "", "| Time (UTC) | Actor | Action | Detail |", "|---|---|---|---|"]
    for a in p.audit:
        if a.action in ("param.set", "param.confirm", "doc.signoff", "rfi.open", "rfi.respond", "package.build"):
            d = {k: v for k, v in a.detail.items() if k in ("key", "value", "version", "scope", "round_no", "stale_docs", "mode")}
            lines.append(f"| {a.at} | {a.actor} | {a.action} | {json.dumps(d)[:200].replace('|', '/')} |")
    for r in p.rfi_rounds:
        lines += ["", f"## RFI round {r.round_no} ({r.received_at})"]
        lines += [f"- [{'x' if it.resolved else ' '}] {it.text} — affects {', '.join(it.affected_params) or '—'}"
                  + (f"; response: {it.response}" if it.response else "") for it in r.items]
    return Document(doc_id="change_log", title="RFI and change log", filename="08_change_log.md",
                    content="\n".join(lines) + "\n", content_type="text/markdown")


GENERATORS: dict[str, Callable[[Project], Document]] = {
    "application_form": application_form,
    "sld": sld,
    "protection_settings": protection,
    "equipment_list": equipment_list,
    "export_scheme": export_scheme_doc,
    "site_plan": site_plan,
    "bess_report": bess_report,
    "change_log": change_log,
}


def generate_all(p: Project, only: list[str] | None = None) -> tuple[list[str], dict[str, str]]:
    done, errors = [], {}
    for doc_id, fn in GENERATORS.items():
        if only and doc_id not in only:
            continue
        try:
            p.put_document(fn(p))
            done.append(doc_id)
        except (KeyError, ValueError, TypeError) as e:
            errors[doc_id] = str(e)
    return done, errors
