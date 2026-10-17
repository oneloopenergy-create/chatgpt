"""Rule-based single line diagram (SLD) generator.

Generates a project-specific SLD (SVG) from the source of truth for a standard topology. Every value on
the drawing is read from a parameter, and the parameters/versions used are recorded so that any change
marks the drawing as stale.

Topologies: rooftop_pv / ground_pv / pv_bess_ac_coupled / mv_kiosk (MV kiosk, optionally with BESS).
"""
from __future__ import annotations

from html import escape
from typing import Any

from ..core.model import Project
from .symbols import isolator_svg

TOPOLOGIES = {"rooftop_pv", "ground_pv", "pv_bess_ac_coupled", "mv_kiosk"}


class _Svg:
    def __init__(self) -> None:
        self.items: list[str] = []

    def line(self, x1, y1, x2, y2, w=2, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.items.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#111" stroke-width="{w}"{d}/>')

    def rect(self, x, y, w, h, fill="#fff", stroke="#111", sw=1.5, rx=0):
        self.items.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
                          f'stroke="{stroke}" stroke-width="{sw}"/>')

    def circle(self, cx, cy, r):
        self.items.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#fff" stroke="#111" stroke-width="1.5"/>')

    def text(self, x, y, s, size=11, anchor="middle", weight="normal", fill="#111"):
        self.items.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" '
                          f'font-weight="{weight}" fill="{fill}">{escape(str(s))}</text>')

    # ------------------------------------------------------------- symbols
    def breaker(self, x, y, label=None):
        self.rect(x - 7, y - 7, 14, 14)
        self.line(x - 7, y - 7, x + 7, y + 7, w=1.2)
        if label:
            self.text(x + 12, y + 4, label, size=10, anchor="start")

    def isolator(self, x, y, label=None):
        self.items.append(isolator_svg(x, y))
        if label:
            self.text(x + 12, y + 4, label, size=10, anchor="start")

    def transformer(self, x, y, label):
        self.circle(x, y - 9, 13)
        self.circle(x, y + 9, 13)
        self.text(x + 22, y + 4, label, size=11, anchor="start")

    def meter(self, x, y, label):
        self.circle(x, y, 12)
        self.text(x, y + 4, "kWh", size=8)
        self.text(x + 18, y + 4, label, size=10, anchor="start")

    def box(self, x, y, w, h, title, sub=None, fill="#fff"):
        self.rect(x - w / 2, y, w, h, fill=fill, rx=3)
        self.text(x, y + (h / 2 if not sub else h / 2 - 3), title, size=10, weight="bold")
        if sub:
            self.text(x, y + h / 2 + 11, sub, size=9)

    def render(self, w, h) -> str:
        body = "\n  ".join(self.items)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
                f'font-family="Arial, Helvetica, sans-serif" style="max-width:100%;height:auto">\n'
                f'  <rect width="{w}" height="{h}" fill="#fff"/>\n  {body}\n</svg>\n')


def generate_sld(p: Project) -> tuple[str, dict[str, int], list[str]]:
    """Returns (svg, parameters used with versions, to-do items)."""
    used: dict[str, int] = {}
    todo: list[str] = []

    def g(key: str, default: Any = None) -> Any:
        prm = p.params.get(key)
        if prm is None:
            used[key] = 0
            return default
        used[key] = prm.version
        return prm.value

    topology = g("design.topology")
    if topology not in TOPOLOGIES:
        raise ValueError(f"design.topology must be one of {sorted(TOPOLOGIES)}, got {topology!r}")
    pv_inv = g("equipment.pv_inverters", []) or []
    bess = g("equipment.bess", []) or []
    v_supply = g("connection.supply_voltage_v")
    mv = topology == "mv_kiosk" or (v_supply or 0) >= 1000
    central = g("calc.central_protection_required")
    if central is None:
        todo.append("Central protection requirement is unknown; verify applicable DNSP rules")
    if v_supply is None:
        todo.append("Supply voltage missing")
    if not pv_inv and not bess:
        todo.append("No inverter or battery equipment provided")
    export_req = g("export.requested_kw")
    scheme = g("export.scheme")

    branches: list[dict[str, Any]] = [{"kind": "load", "label": "Site load",
                                       "sub": f"Max demand {g('connection.max_demand_kva', '?')} kVA"}]
    for i, inv in enumerate(pv_inv):
        branches.append({"kind": "pv", "inv": inv, "idx": i + 1})
    for i, b in enumerate(bess):
        branches.append({"kind": "bess", "b": b, "idx": i + 1})

    col_w = 150
    width = max(760, 80 + col_w * len(branches))
    s = _Svg()
    cx = 120
    y = 40
    s.box(cx, y, 170, 36, "DNSP network", f"{g('site.dnsp', '?')} · {int(v_supply) if v_supply else '?'} V", fill="#eef4ff")
    y += 36
    s.line(cx, y, cx, y + 30)
    y += 30
    if mv:
        s.breaker(cx, y + 8, "HV incoming switchgear (HV CB)")
        s.line(cx, y + 15, cx, y + 40)
        y += 40
        if central:
            s.text(cx + 120, y - 6, "Central protection 27/59/81/81R/59N → trips HV CB", size=9, anchor="start", fill="#b00")
        tx = g("connection.transformer_kva")
        if tx is None:
            todo.append("Missing kiosk transformer rating connection.transformer_kva")
        s.transformer(cx, y + 22, f"Kiosk TX {tx or '?'} kVA  {int(v_supply or 0) / 1000:g} kV / LV TBC · vector group TBC")
        s.line(cx, y + 44, cx, y + 70)
        y += 70
    s.meter(cx, y + 12, f"Revenue meter NMI {g('site.nmi', 'TBC')}")
    y += 24
    s.line(cx, y, cx, y + 26)
    y += 26
    s.breaker(cx, y + 8, "Main switch")
    if central and not mv:
        relay = g("design.central_protection_relay")
        s.line(cx + 140, y + 8, cx + 175, y + 8, w=1, dash="3,3")
        s.rect(cx + 175, y - 4, 210, 24, fill="#fff4f4", stroke="#b00")
        s.text(cx + 280, y + 12, f"Central protection 27/59/81/81R · {relay or 'model TBC'}", size=9, fill="#b00")
    y += 16
    s.line(cx, y, cx, y + 20)
    y += 20
    s.rect(cx - 6, y, 12, 18, fill="#fff")
    s.text(cx + 14, y + 13, f"Export limiting CT / meter · scheme {scheme or '?'} · limit {export_req if export_req is not None else '?'} kW",
           size=10, anchor="start")
    y += 18
    s.line(cx, y, cx, y + 26)
    y += 26
    bus_y = y
    x0, x1 = 60, 60 + col_w * len(branches)
    s.line(x0, bus_y, x1, bus_y, w=5)
    s.text(x0, bus_y - 8, f"Main switchboard (MSB) {'LV voltage TBC' if mv else (str(v_supply) + ' V' if v_supply else 'voltage TBC')} busbar", size=11, anchor="start", weight="bold")

    for i, br in enumerate(branches):
        bx = 60 + col_w * i + col_w / 2
        yy = bus_y
        s.line(bx, yy, bx, yy + 30)
        s.breaker(bx, yy + 38)
        s.line(bx, yy + 45, bx, yy + 70)
        yy += 70
        if br["kind"] == "load":
            s.box(bx, yy, 120, 44, br["label"], br["sub"])
            continue
        if br["kind"] == "pv":
            inv = br["inv"]
            s.isolator(bx, yy + 10, "AC isolator")
            s.line(bx, yy + 20, bx, yy + 40)
            qty = int(inv.get("qty", 1))
            s.box(bx, yy + 40, 130, 46, f"PV inverter ×{qty}", f"{inv['manufacturer']} {inv['model']}")
            s.text(bx + 6, yy + 102, f"{inv['rated_ac_kva']} kVA each · {g('inverter.region', '?')}", size=9, anchor="start")
            s.line(bx, yy + 86, bx, yy + 120, dash="5,3")
            s.isolator(bx, yy + 132, "DC isolator")
            s.line(bx, yy + 142, bx, yy + 160, dash="5,3")
            share = inv.get("dc_kwp")
            s.box(bx, yy + 160, 120, 40, "PV array", f"{share} kWp" if share else "kWp per equipment list")
        else:
            b = br["b"]
            qty = int(b.get("qty", 1))
            s.isolator(bx, yy + 10, "AC isolator")
            s.line(bx, yy + 20, bx, yy + 40)
            s.box(bx, yy + 40, 130, 46, f"BESS PCS ×{qty}", f"{b['manufacturer']} {b['model']}")
            s.text(bx + 6, yy + 102, f"{b['pcs_kva']} kVA each", size=9, anchor="start")
            s.line(bx, yy + 86, bx, yy + 120, dash="5,3")
            s.isolator(bx, yy + 132, "DC isolator")
            s.line(bx, yy + 142, bx, yy + 160, dash="5,3")
            s.box(bx, yy + 160, 120, 40, "Battery (AS/NZS 5139)", f"{b.get('energy_kwh', 'TBC')} kWh each", fill="#f3fbf3")

    # summary and title block
    ty = bus_y + 70 + 220
    height = ty + 150
    s.rect(20, ty, width - 40, 130, fill="#fafafa")
    s.text(32, ty + 22, f"Project: {p.name}", size=12, anchor="start", weight="bold")
    s.text(32, ty + 42, f"Site: {g('site.address', 'TBC')}    NMI: {g('site.nmi', 'TBC')}    Topology: {topology}", size=10, anchor="start")
    s.text(32, ty + 60, f"Total inverter AC {g('calc.inverter_ac_kva', '?')} kVA · PV {g('pv.dc_kwp', '?')} kWp · "
                        f"BESS {g('calc.bess_energy_kwh') if g('calc.bess_energy_kwh') is not None else 'TBC'} kWh · Connection path {g('calc.connection_path', '?')}",
           size=10, anchor="start")
    s.text(32, ty + 78, f"Central protection: {'TBC' if central is None else ('required' if central else 'not required')}    Export limiting device: {'TBC' if g('calc.export_limiting_required') is None else ('required' if g('calc.export_limiting_required') else 'not required')}",
           size=10, anchor="start")
    s.text(32, ty + 104, "DRAFT – SUBJECT TO REVIEW AND SIGN-OFF BY A REGISTERED ENGINEER – NOT FOR CONSTRUCTION",
           size=12, anchor="start", weight="bold", fill="#b00")
    s.text(width - 32, ty + 122, "Generated by GridEasy rule engine · parameter versions in project record", size=9, anchor="end", fill="#666")

    if not g("site.nmi"):
        todo.append("NMI missing")
    if central and not mv and not g("design.central_protection_relay"):
        todo.append("Confirm central protection relay model and trip target (main switch shunt trip)")
    for b in bess:
        if b.get("energy_kwh") is None:
            todo.append(f"Battery energy missing for {b['model']}")
    for inv in pv_inv:
        if not inv.get("dc_kwp"):
            todo.append(f"Inverter {inv['model']} has no array kWp assigned")
            break
    return s.render(width, height), used, todo
