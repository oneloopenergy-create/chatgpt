from xml.etree import ElementTree as ET

import pytest

from gridease.sld.generator import generate_sld
from gridease.sld.symbols import isolator_geometry
from .conftest import user


@pytest.mark.parametrize('topology', ['rooftop_pv','ground_pv','pv_bess_ac_coupled','mv_kiosk'])
def test_schemdraw_symbols_are_embedded_in_each_topology(project, topology):
    user(project,'design.topology',topology)
    if topology=='mv_kiosk':
        user(project,'connection.supply_voltage_v',11000)
        user(project,'connection.transformer_kva',1500)
    svg, used, todo=generate_sld(project)
    root=ET.fromstring(svg)
    symbols=[node for node in root.iter() if node.attrib.get('data-symbol-provider')=='schemdraw']
    assert len(symbols)==2*(len(project.get('equipment.pv_inverters'))+len(project.get('equipment.bess')))
    assert all(any(child.tag.endswith('path') for child in symbol) for symbol in symbols)
    assert 'equipment.pv_inverters' in used
    assert 'NOT FOR CONSTRUCTION' in svg
    assert not any(node.tag.endswith('script') for node in root.iter())


def test_sld_escapes_customer_text_with_library_symbols(project):
    project.name='<script>alert("customer")</script>'
    svg, _, _=generate_sld(project)
    root=ET.fromstring(svg)
    assert not any(node.tag.endswith('script') for node in root.iter())
    assert '&lt;script&gt;' in svg
    assert isolator_geometry()==isolator_geometry()
