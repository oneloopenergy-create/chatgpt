"""Connectivity-first engineering SLD, with separately paginated A3 schedules.

Layout conventions were reviewed against the uploaded AU/NZ reference corpus;
reference equipment ratings and protection settings are never used as defaults.
"""
from collections import deque
from html import escape
from textwrap import wrap

from .generator import _Svg

SHEET_W, SHEET_H = 1680, 1188


def value(v):
    return 'TBC' if v is None or v == '' else str(v)


def lines(s, x, y, content, width=65, size=11, step=16):
    for row in wrap(str(content), width=width, break_long_words=True) or ['']:
        s.text(x, y, row, size=size, anchor='start')
        y += step
    return y


def graph_layout(d):
    """Undirected shortest paths: cable endpoint order is not power-flow direction.

    Transformers have an internal electrical link, but their two declared node
    names collapse to a single drawing symbol. Never invent links to orphan assets.
    """
    kinds = {'GRID': 'grid', 'POC': 'poc', d.msb_id: 'bus', d.eg_bus_id: 'bus'}
    kinds.update({b.id: 'bus' for b in d.switchboards})
    kinds.update({b.id: 'isolator' if b.role == 'isolation' else 'breaker' for b in d.breakers})
    kinds.update({t.id: 'transformer' for t in d.transformers})
    kinds.update({e.id: e.kind for e in d.equipment})
    aliases = {node: t.id for t in d.transformers for node in (t.primary_node, t.secondary_node) if node}
    adjacency = {k: [] for k in kinds}
    for c in d.cables:
        a, b = aliases.get(c.from_id, c.from_id), aliases.get(c.to_id, c.to_id)
        if a in kinds and b in kinds and a != b:
            adjacency[a].append(b); adjacency[b].append(a)
    depth = {'GRID': 0}; queue = deque(['GRID'])
    while queue:
        a = queue.popleft()
        for b in adjacency[a]:
            if b not in depth:
                depth[b] = depth[a]+1; queue.append(b)
    disconnected = set(kinds)-set(depth)
    orphan_level = max(depth.values(), default=0)+1
    for k in kinds:
        if k in disconnected: depth[k] = orphan_level
    layers = {}
    for k in kinds: layers.setdefault(depth[k], []).append(k)
    width = max(700, 400*max(map(len, layers.values())))
    positions = {k: ((i+1)*width/(len(keys)+1), 45+90*level)
                 for level, keys in sorted(layers.items()) for i, k in enumerate(keys)}
    return kinds, aliases, positions, disconnected, width, 110+90*max(layers)


def terminal(kind, x, y, end):
    extent = {'grid': 18, 'poc': 5, 'bus': 0, 'breaker': 10,
              'isolator': 15, 'transformer': 32, 'pv': 30, 'bess': 30}[kind]
    return x, y+end*extent


def frame(p, title, number, total):
    d = p.delivery.design; s = _Svg()
    s.rect(18, 18, SHEET_W-36, SHEET_H-36)
    s.text(38, 49, title, size=21, anchor='start', weight='bold')
    s.text(38, 73, p.name, size=13, anchor='start')
    s.text(SHEET_W-38, 49, 'DRAFT / NOT FOR CONSTRUCTION', size=13, anchor='end', fill='#b00', weight='bold')
    s.line(18, 1010, SHEET_W-18, 1010)
    # A recorded checker name is not an electronic signature.
    columns = [(38, 'DRAWING', d.drawing_number), (450, 'REVISION / DATE', f'{value(d.drawing_revision)} / {value(d.drawing_date)}'),
               (860, 'DESIGNER', d.responsible_designer), (1270, 'CHECKER (UNSIGNED)', d.drawing_checker)]
    for x, label, content in columns:
        s.text(x, 1035, label, size=10, anchor='start', weight='bold')
        lines(s, x, 1056, value(content), width=44)
    s.line(18, 1086, SHEET_W-18, 1086)
    lines(s, 38, 1110, f'Company: {value(d.design_company)} | Contact: {value(d.designer_contact)}', width=160)
    from ..delivery.readiness import design_hash
    s.text(38, 1150, f'Project {p.id} | Design {design_hash(p)[:16]} | NTS | Electrical values from entered project records only', size=10, anchor='start')
    s.text(SHEET_W-38, 1150, f'A3 landscape · SHEET {number}/{total}', size=11, anchor='end')
    return s


def render_engineering_sld(p):
    d = p.delivery.design
    kinds, aliases, pos, orphans, gw, gh = graph_layout(d)
    drawing = _Svg()
    # All cable endpoints meet a symbol's actual terminals; junction dots only
    # appear at declared buses/connection points, never at route crossings.
    for index, c in enumerate(d.cables):
        a, b = aliases.get(c.from_id, c.from_id), aliases.get(c.to_id, c.to_id)
        if a not in pos or b not in pos: continue
        x1, y1 = pos[a]; x2, y2 = pos[b]
        if a == b:
            # A cable between transformer windings is not its internal link.
            continue
        downward = y2 > y1
        if y1 == y2:
            start, end = terminal(kinds[a], x1, y1, 1), terminal(kinds[b], x2, y2, 1)
            mid = y1+78+12*(index % 3)
        else:
            start = terminal(kinds[a], x1, y1, 1 if downward else -1)
            end = terminal(kinds[b], x2, y2, -1 if downward else 1)
            mid = (start[1]+end[1])/2+8*(index % 3)
        drawing.items.append(f'<g data-cable="{escape(c.id, quote=True)}">')
        drawing.line(*start, start[0], mid, w=1.5)
        drawing.line(start[0], mid, end[0], mid, w=1.5)
        drawing.line(end[0], mid, *end, w=1.5)
        drawing.text((x1+x2)/2+8, mid-7, c.id, anchor='start', size=11)
        drawing.items.append('</g>')
        if c.id == d.ownership_boundary_cable_id:
            bx, by = (start[0]+end[0])/2, mid
            drawing.items.append('<g data-boundary="ownership">')
            if start[0] == end[0]: drawing.line(bx-65, by, bx+65, by, w=1, dash='7,4')
            else: drawing.line(bx, by-30, bx, by+30, w=1, dash='7,4')
            drawing.text(bx-70, by-7, 'OWNERSHIP BOUNDARY', size=10, anchor='end')
            drawing.items.append('</g>')
    breakers = {b.id: b for b in d.breakers}; equipment = {e.id: e for e in d.equipment}
    transformers = {t.id: t for t in d.transformers}; boards = {b.id: b for b in d.switchboards}
    for key, kind in kinds.items():
        x, y = pos[key]
        drawing.items.append(f'<g data-asset="{escape(key, quote=True)}" data-kind="{kind}">')
        if kind == 'bus':
            drawing.line(x-55, y, x+55, y, w=5); drawing.circle(x, y, 3)
        elif kind == 'poc': drawing.circle(x, y, 5)
        elif kind == 'grid':
            drawing.rect(x-40, y-18, 80, 36); drawing.text(x, y+4, 'NETWORK', size=10)
        elif kind == 'breaker':
            drawing.rect(x-10, y-10, 20, 20); drawing.line(x-10, y-10, x+10, y+10, w=1.2)
        elif kind == 'isolator':
            drawing.circle(x, y-15, 2); drawing.circle(x, y+15, 2)
            drawing.line(x, y+15, x+13, y-10, w=1.5)
        elif kind == 'transformer':
            drawing.circle(x, y-12, 20); drawing.circle(x, y+12, 20)
        else:
            drawing.rect(x-30, y-30, 60, 60)
            drawing.line(x-30, y+30, x+30, y-30, w=1)
            drawing.text(x-15, y-6, '~', size=20); drawing.text(x+15, y+21, '=', size=19)
        label = key
        details = []
        if key in boards:
            b = boards[key]; label += f' / {b.label}'; details = [f'{b.installation_status} · {value(b.phases)} · {value(b.location)}']
        elif key in breakers:
            b = breakers[key]; details = [f'{b.role} · {value(b.rating_a)} A · {value(b.breaking_ka)} kA · {b.poles}P', f'{b.trip_coil} coil / {value(b.coil_voltage_v)} V']
        elif key in transformers:
            t = transformers[key]; details = [f'{value(t.rating_kva)} kVA · {value(t.primary_v)}/{value(t.secondary_v)} V', f'Z={value(t.impedance_pct)}% · {value(t.vector_group)}']
        elif key in equipment:
            e = equipment[key]; label += f' / {e.qty} × {e.kind.upper()}'
            details = [f'{e.manufacturer} {e.model}', f'{value(e.rated_kva)} kVA / {value(e.rated_kw)} kW per unit']
        drawing.text(x+75, y-12, label if len(label)<=43 else label[:40]+'…', anchor='start', size=12, weight='bold')
        yy = y+7
        for detail in details:
            short = detail if len(detail)<=68 else detail[:65]+'…'
            yy = lines(drawing, x+75, yy, short, width=35, size=10, step=13)
        if key in orphans: drawing.text(x+75, yy+12, 'UNCONNECTED — CHECK CABLES', anchor='start', size=10, fill='#b00')
        drawing.items.append('</g>')
    # Instruments reference an asset; no invented primary cable or secondary route.
    offsets = {}
    for instrument in d.instruments:
        key = aliases.get(instrument.location_id, instrument.location_id)
        if key not in pos: continue
        x, y = pos[key]; offset = offsets.get(key, 0); offsets[key] = offset+1
        ix, iy = x-90-65*offset, y
        drawing.line(ix+12, iy, x, y, w=1, dash='3,3')
        drawing.circle(ix, iy, 12); drawing.text(ix, iy+4, instrument.kind, size=8)
        drawing.text(ix, iy-20, instrument.id, size=9)
    # Schedules retain all data, wrapped and paginated rather than clipped.
    records = [('EQUIPMENT SCHEDULE', 'Qty, per-unit rating, certification reference; no example ratings imported')]
    for e in d.equipment:
        records.append((e.id, f'{e.qty} × {e.kind.upper()} | {e.manufacturer} {e.model} | {value(e.rated_kva)} kVA / {value(e.rated_kw)} kW per unit | Battery {value(e.energy_kwh)} kWh per unit | PV DC {value(e.dc_kwp)} kWp per group | CEC {value(e.cec_reference)}'))
    records.append(('CABLE SCHEDULE', 'Actual endpoints; verify sizing, installation and voltage-rise study separately'))
    for c in d.cables:
        records.append((c.id, f'{c.from_id} → {c.to_id} | {value(c.cores)} | {value(c.size_mm2)} mm² {c.material} | {value(c.length_m)} m | {value(c.installation)} | Iz {value(c.current_capacity_a)} A | Source {value(c.source_ref)}'))
    records.append(('CT / VT SCHEDULE', 'Dashed diagram leaders identify installation assets; they do not represent secondary wiring. See protection schematic.'))
    for i in d.instruments:
        records.append((i.id, f'{i.kind} at {i.location_id} | {i.purpose} | {i.phases} | {value(i.ratio_primary)}/{value(i.ratio_secondary)} | Class {value(i.accuracy_class)} | {value(i.burden_va)} VA | Winding {value(i.winding)} | Terminals {value(i.secondary_terminals)} → {value(i.relay_input)} | Earth {value(i.earthing)}'))
    pages = []; rows = []; y = 115
    for label, content in records:
        wrapped = wrap(content, 165, break_long_words=True) or ['TBC']
        # Split arbitrarily long user-entered notes without overflowing a sheet.
        while wrapped:
            available = max(1, int((980-y-30)//18))
            chunk, wrapped = wrapped[:available], wrapped[available:]
            rows.append((y, label, chunk)); y += 32+18*len(chunk)
            if wrapped or y > 900:
                pages.append(rows); rows = []; y = 115
                if wrapped: label += ' (continued)'
    if rows: pages.append(rows)
    total = 1+len(pages)
    sheets = [frame(p, 'ELECTRICAL SINGLE LINE DIAGRAM', 1, total)]
    s = sheets[0]
    lines(s, 38, 105, f'Connection point: {value(d.connection_point)} | Ownership boundary (description only): {value(d.ownership_boundary)}', width=180)
    s.text(38, 147, 'Legend: solid = entered power cable; dashed = instrument location leader; converter = PV / PCS; open blade = isolator (state not specified)', size=11, anchor='start')
    # Uniform scaling preserves symbol proportions. Main topology has its own
    # viewBox, separate from the fixed A3 frame and readable schedule sheets.
    s.items.append(f'<svg x="35" y="170" width="1610" height="820" viewBox="0 0 {gw+320} {gh}" preserveAspectRatio="xMidYMid meet">'+''.join(drawing.items)+'</svg>')
    for number, rows in enumerate(pages, 2):
        s = frame(p, 'SLD — EQUIPMENT / CABLE / INSTRUMENT SCHEDULES', number, total)
        for y, label, content in rows:
            s.line(38, y-12, 1640, y-12, w=.6)
            s.text(38, y+4, label, anchor='start', weight='bold', size=12)
            for n, row in enumerate(content): s.text(38, y+26+18*n, row, anchor='start', size=12)
        sheets.append(s)
    # Sheet metadata supports downstream print/export without guessing page size.
    result = _Svg()
    for i, s in enumerate(sheets):
        result.items.append(f'<svg data-sheet="{i+1}" x="0" y="{i*SHEET_H}" width="{SHEET_W}" height="{SHEET_H}" viewBox="0 0 {SHEET_W} {SHEET_H}">'+''.join(s.items)+'</svg>')
    return result.render(SHEET_W, SHEET_H*len(sheets))


def printable_sld(svg):
    """Print each generated sheet at A3 landscape, without rasterising its lines."""
    from xml.etree import ElementTree as ET
    root = ET.fromstring(svg)
    sheets = [node for node in root if node.get('data-sheet')]
    if not sheets:
        sheets = [root]
    pages = []
    for node in sheets:
        node.set('x', '0'); node.set('y', '0')
        node.set('width', '100%'); node.set('height', '100%')
        pages.append('<section class="sheet">'+ET.tostring(node, encoding='unicode')+'</section>')
    return '''<!doctype html><html><meta charset="utf-8"><title>SLD — A3 drawing sheets</title>
<style>@page{size:A3 landscape;margin:0}body{margin:0;background:#ddd}.sheet{width:420mm;height:297mm;background:white;margin:12px auto;break-after:page;overflow:hidden}.sheet:last-child{break-after:auto}.sheet svg{display:block;font-family:Arial,Helvetica,sans-serif}@media print{body{background:white}.sheet{margin:0}}</style>'''+''.join(pages)+'</html>'
