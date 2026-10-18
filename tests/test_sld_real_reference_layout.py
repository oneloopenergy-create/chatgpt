"""Deidentified structural regressions inspired by reference drawings, not their ratings."""
from xml.etree import ElementTree as ET

import pytest
from pydantic import ValidationError
from gridease.delivery.model import Design, Delivery
from gridease.core.model import Project
from gridease.sld.engineering import graph_layout, render_engineering_sld, terminal, printable_sld
from gridease.sld.references import reference_catalog
from .test_delivery import client, create_complete_design, design_data

NS = {'s': 'http://www.w3.org/2000/svg'}


def project(data=None):
    return Project(name='Structural regression', delivery=Delivery(design=Design.model_validate(data or design_data())))


def test_reversed_cable_endpoints_keep_radial_layout_and_real_terminals():
    d = Design.model_validate(design_data())
    kinds, _, positions, orphans, _, _ = graph_layout(d)
    for c in d.cables: c.from_id, c.to_id = c.to_id, c.from_id
    assert graph_layout(d)[2:4] == (positions, orphans)
    svg = ET.fromstring(render_engineering_sld(project(d.model_dump())))
    for c in d.cables:
        group = svg.find(f'.//s:g[@data-cable="{c.id}"]', NS)
        wires = group.findall('s:line', NS)
        a, b = positions[c.from_id], positions[c.to_id]
        downward = b[1] > a[1]
        start = terminal(kinds[c.from_id], *a, 1 if downward else -1)
        end = terminal(kinds[c.to_id], *b, -1 if downward else 1)
        assert tuple(float(wires[0].get(k)) for k in ('x1','y1')) == start
        assert tuple(float(wires[-1].get(k)) for k in ('x2','y2')) == end


def test_multiple_boards_and_orphans_are_not_invented_connections(client):
    p, data = create_complete_design(client)
    data['switchboards'] = [dict(id='PVDB2', label='Additional PV board', phases='L1,L2,L3', installation_status='new')]
    url = f"/api/projects/{p['id']}"
    result = client.put(url+'/delivery/design', json=data)
    assert result.status_code == 200
    assert any('PVDB2: no declared cable path' in item for item in result.json()['workflow'][0]['blockers'])
    svg = client.get(url+'/documents/sld').text
    assert 'UNCONNECTED' in svg and 'Additional PV board' in svg
    data['switchboards'][0]['id'] = 'MSB'
    assert client.put(url+'/delivery/design', json=data).status_code == 422


def test_schedules_paginate_preserve_full_values_and_print_at_a3():
    data = design_data()
    data['equipment'][0]['model'] = '<unsafe>&' + 'Long-model-'*120
    # Many real endpoints without creating extra equipment or guessing ratings.
    data['cables'] += [dict(data['cables'][0], id=f'PARALLEL{i}') for i in range(65)]
    svg = render_engineering_sld(project(data)); root = ET.fromstring(svg)
    sheets = [node for node in root if node.get('data-sheet')]
    assert len(sheets) >= 4
    assert '<unsafe>' not in svg
    assert data['equipment'][0]['model'] in ''.join(root.itertext()).replace('\n','')
    for sheet in sheets:
        # Schedule text is confined above the fixed title block.
        for t in sheet.findall('s:text', NS):
            assert float(t.get('y')) <= 1150
    html = printable_sld(svg)
    assert html.count('<section class="sheet">') == len(sheets)
    assert '@page{size:A3 landscape;margin:0}' in html
    assert ' y="1188"' not in html


def test_reference_catalog_keeps_jurisdiction_and_historical_scope(client):
    rows = reference_catalog()
    assert len(rows) == 24 and {r['country'] for r in rows} == {'AU','NZ'}
    assert all(len(r['sha256']) == 64 and not r['automatic_settings'] for r in rows)
    assert all(r['category'] == 'grid_map' for r in rows if 'grid_line_diagram' in r['id'])
    assert next(r for r in rows if 'EG_register_sample' in r['id'])['category'] == 'historical_guidance'
    assert client.get('/api/delivery/schema').json()['sld_references'] == rows
    p, _ = create_complete_design(client)
    result = client.get(f"/api/projects/{p['id']}/delivery/sld-print")
    assert result.status_code == 200 and '<section class="sheet">' in result.text


def test_boundary_is_only_drawn_for_explicit_cable_and_release_includes_print_view(client):
    import hashlib
    import io
    import json
    import zipfile
    from gridease.delivery.readiness import design_issues
    p, data = create_complete_design(client)
    assert 'data-boundary=' not in render_engineering_sld(project(data))
    data['ownership_boundary_cable_id'] = 'UNKNOWN'
    assert 'Ownership boundary cable is not a declared cable' in design_issues(project(data))
    data['ownership_boundary_cable_id'] = data['cables'][1]['id']
    data['drawing_checker'] = '<Not a signature>'
    url = f"/api/projects/{p['id']}"
    assert client.put(url+'/delivery/design', json=data).status_code == 200
    svg = client.get(url+'/documents/sld').text
    assert 'data-boundary="ownership"' in svg and '&lt;Not a signature&gt;' in svg
    response = client.post(url+'/delivery/releases?scope=design&mode=draft', json={'actor':'Reviewer'})
    assert response.status_code == 200
    release = response.json()['release']
    content = client.get(url+f"/delivery/releases/{release['id']}/download").content
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        manifest = json.loads(z.read('manifest.json'))
        printable = next(d for d in manifest['documents'] if d['id'] == 'sld_print')
        assert hashlib.sha256(z.read(printable['path'])).hexdigest() == printable['sha256']
        assert printable['source_sha256'] == next(d['sha256'] for d in manifest['documents'] if d['id'] == 'sld')
        assert not printable['signed']


def test_multibranch_and_transformer_winding_aliases_preserve_entered_graph():
    data = design_data()
    data['transformers'] = [dict(id='TX1', primary_node='HV_IN', secondary_node='LV_OUT', vector_group='Dyn11')]
    data['switchboards'] = [dict(id='PVDB2', label='New generation board')]
    data['cables'] += [dict(data['cables'][0], id='HV_FEED', from_id='POC', to_id='HV_IN'),
                       dict(data['cables'][0], id='LV_FEED', from_id='LV_OUT', to_id='PVDB2')]
    kinds, aliases, positions, orphans, _, _ = graph_layout(Design.model_validate(data))
    assert aliases['HV_IN'] == aliases['LV_OUT'] == 'TX1'
    assert not orphans
    root = ET.fromstring(render_engineering_sld(project(data)))
    for key in ('HV_FEED','LV_FEED'):
        assert root.find(f'.//s:g[@data-cable="{key}"]', NS) is not None
    assert root.find('.//s:g[@data-asset="TX1"]', NS).get('data-kind') == 'transformer'
