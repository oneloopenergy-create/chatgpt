import zipfile
import io

import pytest
from fastapi.testclient import TestClient

from gridease.api import app as api_module
from gridease.core.model import Project, SignOff
from gridease.core.store import ProjectStore, ProjectConflict
from gridease.package.bundle import blockers
from gridease.package.documents import generate_all
from .conftest import BRIEF, user


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api_module, '_store', ProjectStore(tmp_path))
    return TestClient(api_module.app)


def test_automatic_sld_create_update_download_and_reload(client):
    r = client.post('/api/projects', json={'name': 'Internal job', 'brief': BRIEF})
    assert r.status_code == 201
    p = r.json()
    assert {'sld','protection_schematic','tripping_matrix','site_layout','control_description'} <= {d['doc_id'] for d in p['documents']}
    pid = p['id']
    url = f'/api/projects/{pid}/documents/sld'
    old = client.get(url).text
    updated = client.put(f'/api/projects/{pid}/params/export.requested_kw', json={'value': 90}).json()
    assert 'sld' not in updated['stale_documents']
    assert 'limit 90 kW' in client.get(url).text
    assert old != client.get(url).text
    download = client.get(url + '/download')
    assert download.status_code == 200
    assert 'attachment;' in download.headers['content-disposition']
    assert client.get(f'/api/projects/{pid}').json()['revision'] == updated['revision']


def test_empty_project_and_missing_battery_energy_are_actionable(client):
    p = client.post('/api/projects', json={'name': 'No brief'}).json()
    assert 'sld' in p['document_errors']
    p = client.post('/api/projects', json={'name': 'Battery', 'brief': 'Ausgrid battery 2 x Sungrow SC125HV, 400 V'}).json()
    assert p['params']['calc.bess_energy_kwh']['value'] is None
    svg = client.get(f"/api/projects/{p['id']}/documents/sld").text
    assert 'TBC kWh each' in svg


@pytest.mark.parametrize('key,value', [
    ('connection.supply_voltage_v', 0), ('export.requested_kw', -1),
    ('equipment.pv_inverters', [{}]), ('equipment.bess', 'bad'),
    ('equipment.pv_inverters', [{'manufacturer':'X','model':'Y','rated_ac_kva':10,'qty':1.5}]),
    ('site.dnsp', 'Unknown'), ('design.topology','unknown'),
    ('bess.round_trip_eff', 0), ('bess.round_trip_eff', 1.5),
    ('load.profile_kw', [1,2]), ('tariff.peak_hours', [-1]),
])
def test_bad_inputs_do_not_change_saved_project(client, key, value):
    p = client.post('/api/projects',json={'name':'Input checks','brief':BRIEF}).json()
    url = f"/api/projects/{p['id']}"
    assert client.put(url + '/params/' + key, json={'value': value}).status_code == 422
    assert client.get(url).json()['revision'] == p['revision']


def test_batch_edit_is_atomic_and_recalculates_once(client):
    p = client.post('/api/projects',json={'name':'Batch','brief':BRIEF}).json()
    url=f"/api/projects/{p['id']}"
    updates=[{'key':'site.address','value':'New address'},{'key':'connection.supply_voltage_v','value':0}]
    assert client.put(url+'/parameters',json={'updates':updates}).status_code==422
    assert 'site.address' not in client.get(url).json()['params']
    updates[1]['value']=415
    r=client.put(url+'/parameters',json={'updates':updates})
    assert r.status_code==200
    assert r.json()['revision']==p['revision']+1
    assert '415 V busbar' in client.get(url+'/documents/sld').text


def test_negative_rfi_index_does_not_edit_last_item(client):
    p=client.post('/api/projects',json={'name':'RFI','brief':BRIEF}).json()
    url=f"/api/projects/{p['id']}"
    client.post(url+'/rfi',json={'items':[{'text':'First item'}]})
    assert client.post(url+'/rfi/0/respond',json={'item_index':0,'response':'test'}).status_code==404
    assert client.post(url+'/rfi/1/respond',json={'item_index':-1,'response':'test'}).status_code==422
    assert not client.get(url).json()['rfi_rounds'][0]['items'][0]['resolved']


def test_empty_identity_and_scope_rejected(client):
    assert client.post('/api/projects',json={'name':'   '}).status_code==422
    p=client.post('/api/projects',json={'name':'Sign','brief':BRIEF}).json()
    url=f"/api/projects/{p['id']}"
    assert client.post(url+'/signoff',json={'reviewer_name':' ','registration_type':'NER','registration_no':'1','scope':['sld']}).status_code==422
    assert client.post(url+'/signoff',json={'reviewer_name':'Engineer','registration_type':'NER','registration_no':'1','scope':[]}).status_code==422


def test_store_prevents_lost_updates_and_resurrection(tmp_path):
    store=ProjectStore(tmp_path)
    p=store.save(Project(name='Original'))
    first, second=store.load(p.id), store.load(p.id)
    first.name='First editor';store.save(first)
    second.name='Second editor'
    with pytest.raises(ProjectConflict): store.save(second)
    assert store.load(p.id).name=='First editor'
    store.delete(p.id)
    with pytest.raises(ProjectConflict): store.save(first)


def test_adding_previously_absent_parameter_invalidates_document(project):
    generate_all(project)
    assert 'site.survey_kmz' not in project.params
    user(project,'site.survey_kmz','survey.kmz')
    assert 'site_plan' in project.stale_documents()


def test_stale_document_is_not_signed(project):
    generate_all(project)
    project.sign(SignOff(reviewer_name='Engineer',registration_type='NER',registration_no='1',scope=['sld']))
    user(project,'site.nmi','4103999999')
    assert not project.is_signed('sld')
    assert any('regeneration' in b for b in blockers(project))


def test_unknown_protection_not_shown_as_not_required(client):
    p=client.post('/api/projects',json={'name':'Unknown protection','brief':'Endeavour Energy 1 x SMA STP 110-60, 400 V'}).json()
    svg=client.get(f"/api/projects/{p['id']}/documents/sld").text
    # Endeavour may have a sourced threshold; force absent capacity with a blank brief instead.
    p=client.post('/api/projects',json={'name':'Unknown capacity','brief':'Ausgrid rooftop'}).json()
    svg=client.get(f"/api/projects/{p['id']}/documents/sld").text
    assert 'Central protection: TBC' in svg
    assert 'Export limiting device: TBC' in svg
    assert '400 V busbar' not in svg


def test_stale_browser_revision_rejected(client):
    p=client.post('/api/projects',json={'name':'Two employees','brief':BRIEF}).json()
    url=f"/api/projects/{p['id']}"
    headers={'X-Project-Revision':str(p['revision'])}
    assert client.put(url+'/params/export.requested_kw',json={'value':80},headers=headers).status_code==200
    r=client.put(url+'/params/export.requested_kw',json={'value':60},headers=headers)
    assert r.status_code==409
    assert client.get(url).json()['params']['export.requested_kw']['value']==80


def test_zero_quantity_in_brief_is_validation_error(client):
    r=client.post('/api/projects',json={'name':'Bad battery','brief':'Ausgrid battery 0 x Sungrow SC125HV totalling 500 kWh, 400 V'})
    assert r.status_code==422
    assert client.get('/api/projects').json()==[]


def test_missing_documents_block_final_even_with_no_findings(monkeypatch):
    from gridease.package import bundle
    monkeypatch.setattr(bundle,'run_checks',lambda p:[])
    assert 'Required document missing: sld' in blockers(Project(name='Missing documents'))


def test_repeated_unit_preserving_edit_does_not_invalidate_signoff(project):
    from gridease.core.model import Source, SourceKind
    src=Source(kind=SourceKind.USER_INPUT,ref='ui')
    first=project.set_param('export.requested_kw',100,src,unit='kW')
    second=project.set_param('export.requested_kw',100,src)
    assert first.version==second.version


def test_missing_economics_inputs_reported_instead_of_zero_tariffs(client):
    p=client.post('/api/projects',json={'name':'Economics','brief':BRIEF}).json()
    r=client.post(f"/api/projects/{p['id']}/bess")
    assert r.status_code==400
    assert 'tariff.import_peak_c_per_kwh' in r.json()['detail']


def test_invalid_licence_date_cannot_break_project(client):
    p=client.post('/api/projects',json={'name':'Licence','brief':BRIEF}).json()
    url=f"/api/projects/{p['id']}"
    assert client.put(url+'/params/contractor.licence_expiry',json={'value':'not-a-date'}).status_code==422
    assert client.get(url).status_code==200


def test_changed_address_does_not_keep_old_calculated_postcode(project):
    from gridease.calc.engineering import run_all
    user(project,'site.address','1 Test Street NSW 2000'); run_all(project)
    assert project.get('site.postcode')=='2000'
    user(project,'site.address','New address without postcode'); run_all(project)
    assert project.get('site.postcode') is None


def test_clearing_inputs_removes_obsolete_calculations_and_rules(client):
    p=client.post('/api/projects',json={'name':'Clear inputs','brief':BRIEF}).json()
    url=f"/api/projects/{p['id']}"
    r=client.put(url+'/parameters',json={'updates':[
        {'key':'site.dnsp','value':None,'remove':True},
        {'key':'connection.supply_voltage_v','value':None,'remove':True},
    ]})
    assert r.status_code==200
    params=r.json()['params']
    assert 'rules.dnsp_pack' not in params
    assert 'calc.rated_current_a' not in params
    svg=client.get(url+'/documents/sld').text
    assert 'Central protection: TBC' in svg
    assert 'voltage TBC' in svg
