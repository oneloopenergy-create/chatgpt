"""Synthetic project fixtures test software gates, not actual engineering certification."""
import base64
import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient
from gridease.api import app as app_module
from gridease.core.model import Project,Source,SourceKind,SignOff
from gridease.core.store import ProjectStore
from gridease.delivery.model import Design,Delivery,Evidence
from gridease.delivery.readiness import design_hash,stage_hash,design_issues,workflow
from gridease.delivery.storage import get_blob
from .conftest import BRIEF,user


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(app_module,'_store',ProjectStore(tmp_path))
    return TestClient(app_module.app)


def design_data():
    breakers=[]
    for bid,role in [('CB_IN','incomer'),('CB_EG','eg_common'),('CB_PV1','branch'),('ISO1','isolation')]:
        breakers.append(dict(id=bid,role=role,location='MSB room',rating_a=1000,breaking_ka=50,trip_coil='undervoltage' if role=='eg_common' else 'none',coil_voltage_v=240,coil_supply='DC/UPS supply S1',coil_terminal='XT1:1/2',feedback_terminal='XT1:3/4',fail_position='open'))
    edges=[('GRID','POC'),('POC','CB_IN'),('CB_IN','MSB'),('MSB','CB_EG'),('CB_EG','EG_BUS'),('EG_BUS','CB_PV1'),('CB_PV1','ISO1'),('ISO1','PV1')]
    cables=[dict(id=f'C{i+1}',from_id=a,to_id=b,cores='4C + PE',material='Cu',size_mm2=300,length_m=5,installation='tray; engineering fixture only',current_capacity_a=1000,r_ohm_per_km=.08,x_ohm_per_km=.07,source_ref='Synthetic cable source') for i,(a,b) in enumerate(edges)]
    protection=[]
    for i,ansi in enumerate(['27','59','81U','81O','81R','78','32R','watchdog','loss_of_mains']):
        required=ansi in ('27','59','81U','81O','watchdog','loss_of_mains','32R')
        protection.append(dict(id=f'F{i+1}',ansi=ansi,name=ansi,applicability='required' if required else 'not_applicable',applicability_basis='Synthetic source clause',relay_model='Test relay',relay_input='V1/V2/V3',output_contact='WATCHDOG_OUT' if ansi=='watchdog' else 'OUT1',output_mode='healthy_closed_trip_open',output_test_link='TBO1',local_indication='HMI/LED function indication',terminal='XT1:1/2',setting=1,setting_unit='test-unit',delay_s=.1,target_breakers=['CB_EG'],setting_source='Synthetic approved schedule',fail_safe='Open CB_EG'))
    items=[dict(id='SITE_POC',kind='connection',label='POC',x_m=0,y_m=0),dict(id='SITE_BOUND',kind='boundary',label='Ownership',x_m=1,y_m=0),dict(id='SITE_MSB',kind='switchboard',label='MSB',x_m=5,y_m=4),dict(id='SITE_PV',kind='pv',label='PV',x_m=10,y_m=10,equipment_ids=['PV1']),dict(id='SITE_ACCESS',kind='access',label='Access',x_m=0,y_m=10)]
    assessments=[dict(id='A'+str(i),kind=kind,location='POC',result=1,upper_limit=2,method='Synthetic study method',limit_source='Synthetic clause; not an engineering limit',reviewer='Test Engineer') for i,kind in enumerate(['voltage_thd_pct','current_thd_pct','flicker_pst','flicker_plt','voltage_change_pct','fault_ka','discrimination'])]
    data = dict(responsible_designer='Test Engineer',designer_contact='test@example.invalid',drawing_revision='T1',operating_modes='Grid-parallel PV only',existing_generation_description='No pre-existing EG; synthetic fixture',connection_point='Fixture POC',ownership_boundary='Fixture boundary',relay_model='Test relay',relay_manufacturer='Test manufacturer',relay_order_code='TEST-ORDER',relay_full_settings_reference='Test complete settings export',site_survey_reference='Synthetic surveyed coordinate dataset',site_coordinates_verified_by='Test Surveyor',source_fault_mva=10,source_x_r=10,upstream_fault_limit_ka=50,breakers=breakers,cables=cables,equipment=[dict(id='PV1',kind='pv',manufacturer='SMA',model='STP 110-60',qty=3,rated_kva=110,rated_kw=110,dc_kwp=300,cec_reference='Synthetic CEC verification',as4777_compliant=True,adjusted_settings_reference='Synthetic settings schedule',cec_expiry='2030-12-31',branch_cb='CB_PV1',connection_node='PV1')],instruments=[dict(id='CT_PROT',kind='CT',purpose='protection',location_id='CB_EG',ratio_primary=1000,ratio_secondary=1,accuracy_class='5P20',burden_va=10,winding='star; S2 single-point earth',secondary_terminals='XT2:1-6',relay_input='I1/I2/I3',earthing='XT2:PE',test_block='TB1',source_ref='Synthetic datasheet'),dict(id='CT_METER',kind='CT',purpose='metering',location_id='MSB',ratio_primary=1000,ratio_secondary=5,accuracy_class='0.5S',burden_va=10,winding='star',secondary_terminals='XT3:1-6',source_ref='Synthetic meter datasheet')],protection=protection,site_items=items,site_routes=[dict(id='ROUTE'+str(i),cable_id=c['id'],item_ids=['SITE_POC','SITE_MSB','SITE_PV']) for i,c in enumerate(cables)],control=dict(controller='Test controller',measurement_ct='CT_METER',soft_limit_kw=100,hard_limit_kw=150,response_s=1,response_source='Synthetic connection-specific requirement',communication_protocol='DNP3',loss_of_comms_action='Open CB_EG',loss_of_power_action='Open CB_EG',watchdog_action='Open CB_EG',trip_breaker_ids=['CB_EG'],independent_trip_path='UPS hardwired relay path',recovery_interlock='Manual reset after witnessed restoration',reconnection_healthy_s=60,trip_signal_over_comms=False,grid_intertrip=False,main_protection_supply='MAIN_1',backup_protection_supply='BACKUP_2',independent_supply_source='Synthetic independently verified circuits',rtu_model='Test RTU'),msb=dict(manufacturer='Synthetic board maker',assembly_id='MSB-001',modified=True,rating_a=1600,short_time_ka=50,duration_s=1,prospective_fault_ka=10,temperature_rise_reference='TEMP1',discrimination_reference='DISC1',standard_edition='AS/NZS 61439 — fixture edition'),policy=dict(source_document_id='NS194-Rev5-20260910',site_type='commercial',backstop_status='enabled',backstop_basis='Synthetic project-specific applicability',title='Synthetic requirements fixture',dnsp='Ausgrid',document_reference='TEST-ONLY-NOT-OFFICIAL',edition='test',clause='test',applicability='Synthetic project solely for software validation',source_url='https://example.invalid/test-only',reviewed_by='Test Engineer',reviewed_on='2026-10-18',status='reviewed',msb_declaration='required',msb_basis='Synthetic clause',communication_mode='SCADA',communication_basis='Synthetic project-specific agreement'),assessments=assessments,operating_point=dict(source_pu=1,load_bus='MSB',load_kw=100,load_kvar=20,dispatch=[dict(equipment_id='PV1',active_kw=0,reactive_kvar=0)],study_reference='Synthetic validation snapshot'))
    data['instruments'][0]['circuits']=[dict(id=f'CT_CIRCUIT{i}',phase=phase,secondary_s1=f'CT:{i}S1',secondary_s2=f'CT:{i}S2',test_input=f'TB:{i}A',test_return=f'TB:{i}B',relay_input=f'R:I{i}',relay_return=f'R:IR{i}',earth_terminal='PE1') for i,phase in enumerate(('L1','L2','L3'),1)]
    return data



def create_complete_design(client):
    p=client.post('/api/projects',json={'name':'Synthetic delivery project','brief':BRIEF}).json()
    pid=p['id'];url='/api/projects/'+pid
    changes={'site.customer':'Test Client','site.address':'Test address NSW 2000','contractor.licence_no':'TEST-LICENCE','generation.max_kw':330,'site.existing_eg_present':False,'design.central_protection_relay':'Test relay','design.export_limiter':'Test controller'}
    for key,value in changes.items():assert client.put(url+'/params/'+key,json={'value':value}).status_code==200
    data=design_data();r=client.put(url+'/delivery/design',json=data)
    assert r.status_code==200,r.text
    return r.json(),data


def evidence(client,pid,kind):
    r=client.post(f'/api/projects/{pid}/delivery/evidence',json={'actor':'Test Uploader','kind':kind,'filename':kind+'.txt','content_base64':base64.b64encode(('Synthetic fixture: '+kind).encode()).decode(),'issuer':'Test issuer','reference':'TEST-'+kind})
    assert r.status_code==201,r.text
    eid=r.json()['delivery']['evidence'][-1]['id']
    r=client.post(f'/api/projects/{pid}/delivery/evidence/{eid}/review',json={'actor':'Test Reviewer','status':'accepted','notes':'Synthetic test fixture only; not actual engineering certification'})
    assert r.status_code==200,r.text
    return eid


def test_typed_design_generates_drawings_and_tracks_real_connectivity(client):
    p,data=create_complete_design(client)
    assert design_issues(Project.model_validate(app_module.store().load(p['id']).model_dump()))==[]
    docs={d['doc_id']:d for d in p['documents']}
    assert {'sld','protection_schematic','tripping_matrix','site_layout','control_description','msb_statement','technical_review','application_schedule','commissioning_plan','secondary_injection_report','communications_report','handover_register'}<=set(docs)
    svg=client.get(f"/api/projects/{p['id']}/documents/sld").text
    assert 'CB_EG' in svg and '5P20' in svg and '300' in svg and 'Fixture boundary' in svg
    data['cables'].append(dict(data['cables'][0],id='BYPASS',from_id='MSB',to_id='PV1'))
    changed=client.put(f"/api/projects/{p['id']}/delivery/design",json=data).json()
    assert any('bypasses' in v for v in changed['workflow'][0]['blockers'])


def test_cannot_skip_stage_or_forge_upload_acceptance(client):
    p=client.post('/api/projects',json={'name':'Incomplete'}).json();url=f"/api/projects/{p['id']}/delivery"
    assert client.post(url+'/stages/energisation/complete',json={'actor':'Employee'}).status_code==409
    assert client.post(url+'/releases?mode=final',json={'actor':'Employee'}).status_code==409
    bad=client.post(url+'/evidence',json={'actor':'Employee','kind':'permission_to_connect','filename':'permit.pdf','content_base64':'invalid','issuer':'DNSP','reference':'X'})
    assert bad.status_code==422
    assert client.get(f"/api/projects/{p['id']}").json()['workflow'][-1]['status']=='blocked'


def test_evidence_integrity_staleness_and_download(client):
    p,data=create_complete_design(client);pid=p['id'];eid=evidence(client,pid,'cec_certificate')
    r=client.get(f'/api/projects/{pid}/delivery/evidence/{eid}/download')
    assert r.status_code==200 and r.content==b'Synthetic fixture: cec_certificate'
    data['ownership_boundary']='Changed boundary'
    client.put(f'/api/projects/{pid}/delivery/design',json=data)
    r=client.post(f'/api/projects/{pid}/delivery/evidence/{eid}/review',json={'actor':'Reviewer','status':'accepted','notes':'Attempt to reuse old evidence'})
    assert r.status_code==409
    e=app_module.store().load(pid).delivery.evidence[0]
    path=app_module.store().root.parent/'attachments'/pid/e.sha256
    path.write_bytes(b'TAMPERED')
    assert client.get(f'/api/projects/{pid}/delivery/evidence/{eid}/download').status_code==409


def test_release_is_immutable_and_contains_evidence(client):
    p,data=create_complete_design(client);pid=p['id'];evidence(client,pid,'site_survey')
    r=client.post(f'/api/projects/{pid}/delivery/releases?mode=draft',json={'actor':'Employee'})
    assert r.status_code==200,r.text
    release=r.json()['release'];url=f"/api/projects/{pid}/delivery/releases/{release['id']}/download"
    original=client.get(url).content
    with zipfile.ZipFile(io.BytesIO(original)) as z:
        assert any(n.startswith('evidence/') for n in z.namelist())
        manifest=json.loads(z.read('manifest.json'));assert manifest['scope']=='design'
        assert 'secondary_injection_report' not in [d['id'] for d in manifest['documents']]
    data['connection_point']='Changed POC'
    client.put(f'/api/projects/{pid}/delivery/design',json=data)
    assert client.get(url).content==original


def test_dss_explicit_model_solves_and_checks_loading(client):
    pytest.importorskip('opendssdirect',reason='Optional native engineering engine is not installed')
    p,data=create_complete_design(client);pid=p['id']
    r=client.post(f'/api/projects/{pid}/delivery/simulate',json={'actor':'Engineer'})
    assert r.status_code==200,r.text
    result=r.json()['delivery']['simulation']
    assert result['frequency_hz']==50 and result['converged']
    assert 100<result['source_kw']<102
    assert len(result['loading_pct'])==8
    data['cables'][0]['r_ohm_per_km']=None
    client.put(f'/api/projects/{pid}/delivery/design',json=data)
    assert client.post(f'/api/projects/{pid}/delivery/simulate',json={'actor':'Engineer'}).status_code==422


def test_file_references_do_not_invalidate_their_own_design_hash(client):
    p,data=create_complete_design(client);before=p['delivery_hash']
    eid=evidence(client,p['id'],'standard')
    data['policy']['evidence_id']=eid
    r=client.put(f"/api/projects/{p['id']}/delivery/design",json=data)
    assert r.json()['delivery_hash']==before


def test_equipment_parameters_cannot_diverge_from_engineering_schedule(client):
    p,_=create_complete_design(client)
    assert client.put(f"/api/projects/{p['id']}/params/equipment.pv_inverters",json={'value':[]}).status_code==409
    assert client.put(f"/api/projects/{p['id']}/params/delivery.design",json={'value':{}}).status_code==400


def prepare_pre_submission(client,monkeypatch):
    import hashlib
    from gridease.delivery.standards import CATALOG
    monkeypatch.setitem(CATALOG['NS194-Rev5-20260910'],'sha256',hashlib.sha256(b'Synthetic fixture: standard').hexdigest())
    p,data=create_complete_design(client);pid=p['id'];url=f'/api/projects/{pid}'
    kinds=['standard','cec_certificate','site_survey','msb_declaration','temperature_rise','discrimination','pq_study','fault_study']
    ids={kind:evidence(client,pid,kind) for kind in kinds}
    data['policy']['evidence_id']=ids['standard']
    for e in data['equipment']:e['cec_evidence_id']=ids['cec_certificate']
    for a in data['assessments']:a['evidence_id']=ids['fault_study' if a['kind']=='fault_ka' else 'discrimination' if a['kind']=='discrimination' else 'pq_study']
    r=client.put(url+'/delivery/design',json=data);assert r.status_code==200,r.text
    p=r.json()
    for key in p['assumptions']:
        assert client.post(url+'/params/'+key+'/confirm',json={'engineer':'Test Engineer'}).status_code==200
    p=client.get(url).json()
    required=['sld','protection_schematic','tripping_matrix','site_layout','control_description','msb_statement','technical_review','application_schedule']
    r=client.post(url+'/signoff',json={'reviewer_name':'Test Engineer','registration_type':'NER','registration_no':'TEST-ONLY','scope':required});assert r.status_code==200
    for stage in ('sld','design_pack','pre_submission'):
        r=client.post(url+f'/delivery/stages/{stage}/complete',json={'actor':'Test Engineer'})
        assert r.status_code==200,r.text
    p=r.json()
    assert [s['status'] for s in p['workflow'][:3]]==['complete']*3
    assert p['workflow'][5]['status']=='blocked'
    return pid,data,ids


def test_full_pre_submission_is_independent_of_later_site_tests(client,monkeypatch):
    pid,data,ids=prepare_pre_submission(client,monkeypatch)
    url=f'/api/projects/{pid}'
    r=client.post(url+'/delivery/releases?mode=final&scope=design',json={'actor':'Employee'})
    assert r.status_code==200,r.text
    # No automatic website submission or fabricated official identifier.
    p=client.get(url).json()
    assert not p['delivery']['design']['milestones']['job_number']
    assert client.post(url+'/submitted').status_code==409


def test_all_seven_stages_require_real_records_and_are_revision_safe(client,monkeypatch):
    pid,data,ids=prepare_pre_submission(client,monkeypatch);url=f'/api/projects/{pid}'
    def save():
        r=client.put(url+'/delivery/design',json=data);assert r.status_code==200,r.text
        return r.json()
    def complete(stage):
        r=client.post(url+f'/delivery/stages/{stage}/complete',json={'actor':'Test Engineer'})
        assert r.status_code==200,r.text + str(client.get(url).json()['workflow'])
    def sign():
        r=client.post(url+'/signoff',json={'reviewer_name':'Test Engineer','registration_type':'NER','registration_no':'TEST-ONLY','scope':['sld','protection_schematic','tripping_matrix','site_layout','control_description','msb_statement','technical_review','application_schedule']})
        assert r.status_code==200,r.text
    data['milestones']={'submission_reference':'TEST-RECEIPT','submitted_on':'2026-10-18','submitted_by':'Test Employee'}
    save();evidence(client,pid,'submission_receipt');complete('submission')
    # Offer metadata arrives later; this must not erase the completed submission.
    data['milestones'].update(offer_reference='TEST-OFFER',accepted_on='2026-10-18',payment_reference='TEST-PAY',job_number='TEST-JOB',der_register_number='TEST-DER')
    save()
    for kind in ['connection_offer','approved_drawings','approved_settings','payment','der_registration']:
        ids[kind]=evidence(client,pid,kind)
    for f in data['protection']:
        if f['applicability']=='required':f['approved_evidence_id']=ids['approved_settings']
    save();sign();complete('offer')
    assert client.get(url).json()['workflow'][3]['status']=='complete'
    # A typed 'pass' flag alone is insufficient: require signed evidence, actual
    # measured values, calibration, qualified operator, and approved timing basis.
    secondary=evidence(client,pid,'secondary_injection')
    comm=evidence(client,pid,'scada_test')
    for kind in ['approved_test_plan','witness_test']:evidence(client,pid,kind)
    tests=[]
    for f in data['protection']:
        if f['applicability']!='required':continue
        tests.append(dict(id='TEST_'+f['id'],kind='secondary_injection',function_id=f['id'],target_breaker='CB_EG',instrument='Test instrument',calibration_reference='TEST-CAL',injection_value=1,measured_pickup=1,unit='test-unit',measured_time_s=.1,maximum_time_s=.105,tolerance_s=.005,acceptance_source='Synthetic approved test plan',trip_observed=True,outcome='pass',operator='Test Operator',qualification='TEST-QUALIFICATION',performed_on='2026-10-18',evidence_id=secondary))
    tests.append(dict(id='TEST_COMM',kind='communications',outcome='pass',operator='Test Operator',performed_on='2026-10-18',evidence_id=comm))
    for i,scenario in enumerate(['communication_loss','controller_power_loss','watchdog','recovery_interlock']):
        tests.append(dict(id='TEST_FAILSAFE'+str(i),kind='interlock',scenario=scenario,outcome='pass',operator='Test Operator',performed_on='2026-10-18',evidence_id=comm,trip_observed=True,measured_time_s=.2))
    data['tests']=tests;save();complete('commissioning')
    data['milestones'].update(inspection_booking='TEST-BOOKING',inspection_on='2026-10-18',permission_reference='TEST-PERMISSION',energised_on='2026-10-18')
    save()
    for kind in ['ccew','inspection','permission_to_connect']:evidence(client,pid,kind)
    complete('energisation')
    p=client.get(url).json()
    assert [row['status'] for row in p['workflow']]==['complete']*7
    r=client.post(url+'/delivery/releases?mode=final&scope=handover',json={'actor':'Test Employee'})
    assert r.status_code==200,r.text
    data['tests'][0]['outcome']='fail';save()
    p=client.get(url).json()
    assert p['workflow'][5]['status']=='blocked' and p['workflow'][6]['status']=='blocked'
    assert client.post(url+'/delivery/releases?mode=final&scope=handover',json={'actor':'Test Employee'}).status_code==409


def test_ns194_prohibits_generic_shunt_trip_and_enforces_specific_timing(project):
    from gridease.delivery.standards import issues
    project.delivery=Delivery(design=Design.model_validate(design_data()))
    project.delivery.design.breakers[1].trip_coil='shunt'
    messages=issues(project)
    assert any('5.9.2' in x and 'shunt' in x for x in messages)
    project.delivery.design.breakers[1].trip_coil='undervoltage'
    assert not any('5.9.2' in x for x in issues(project))
    c=project.delivery.design.control;c.grid_intertrip=True;c.response_s=6;c.reconnection_healthy_s=59
    assert any('within 5 s' in x for x in issues(project))
    assert any('>=60 s' in x for x in issues(project))


def test_ns238_compatibility_numbers_cannot_be_used_as_customer_allocation(project):
    from gridease.delivery.standards import issues
    project.delivery=Delivery(design=Design.model_validate(design_data()))
    project.delivery.design.policy.pq_source_document_id='NS238-Am0-20150504'
    a=project.delivery.design.assessments[0];a.limit_type='compatibility_screening';a.upper_limit=8;a.result=2
    assert any('not a customer emission allocation' in msg for msg in issues(project))


def test_forged_standard_filename_cannot_substitute_for_exact_source_pdf(client):
    p,data=create_complete_design(client);pid=p['id'];eid=evidence(client,pid,'standard')
    data['policy']['evidence_id']=eid
    p=client.put(f'/api/projects/{pid}/delivery/design',json=data).json()
    assert any('SHA-256' in item for item in p['workflow'][1]['blockers'])


def test_regenerating_after_reload_preserves_unchanged_drawing_signatures(client):
    p,data=create_complete_design(client);url=f"/api/projects/{p['id']}"
    client.post(url+'/signoff',json={'reviewer_name':'Test Engineer','registration_type':'NER','registration_no':'TEST','scope':['site_layout']})
    # Loading JSON coerces default numbers; rendering must remain byte-identical.
    client.put(url+'/delivery/design',json=data)
    p=client.get(url).json()
    assert next(d for d in p['documents'] if d['doc_id']=='site_layout')['signed']


def test_project_delete_removes_only_its_own_attachments_and_releases(client):
    p,_=create_complete_design(client);pid=p['id'];evidence(client,pid,'site_survey')
    client.post(f'/api/projects/{pid}/delivery/releases?mode=draft',json={'actor':'Employee'})
    root=app_module.store().root.parent
    other=root/'attachments'/'OTHERPROJECT';other.mkdir(parents=True);(other/'keep').write_text('preserve')
    assert client.delete('/api/projects/'+pid).status_code==204
    assert not (root/'attachments'/pid).exists()
    assert not (root/'releases'/pid).exists()
    assert (other/'keep').read_text()=='preserve'


def test_hv_transformer_uses_entered_nodes_impedance_and_phase_shift(client):
    pytest.importorskip('opendssdirect',reason='Optional native engineering engine is not installed')
    p,data=create_complete_design(client);url='/api/projects/'+p['id']
    assert client.put(url+'/params/connection.supply_voltage_v',json={'value':11000}).status_code==200
    data['cables'][2]['to_id']='HV_TX1'
    data['cables'].append(dict(data['cables'][2],id='C9',from_id='LV_TX1',to_id='MSB'))
    data['transformers']=[dict(id='TX1',rating_kva=1000,primary_v=11000,secondary_v=400,impedance_pct=5,resistance_pct=1,vector_group='Dyn11',primary_node='HV_TX1',secondary_node='LV_TX1',dss_leadlag='lead',source_ref='Synthetic manufacturer test model')]
    assert client.put(url+'/delivery/design',json=data).status_code==200
    r=client.post(url+'/delivery/simulate',json={'actor':'Engineer'})
    assert r.status_code==200,r.text
    result=r.json()['delivery']['simulation']
    assert result['converged'] and all(220<v<240 for v in result['voltages']['msb'])
    assert 'Dyn11' in client.get(url+'/documents/sld').text


def test_legacy_api_cannot_bypass_engineering_release_checks(client):
    p=client.post('/api/projects',json={'name':'Legacy','brief':BRIEF,'engineering_delivery':False}).json()
    assert client.get(f"/api/projects/{p['id']}/package?mode=final").status_code==409


def test_aliasing_reserved_bus_ids_is_rejected(client):
    p,data=create_complete_design(client)
    data['equipment'][0]['id']='GRID'
    assert client.put(f"/api/projects/{p['id']}/delivery/design",json=data).status_code==422


def test_harmonic_thd_is_calculated_from_explicit_spectrum_and_distinguishes_quantities(client):
    from gridease.delivery.calculations import harmonic_thd,assessment_value
    from gridease.delivery.model import HarmonicStudy,Assessment
    spectrum=HarmonicStudy(id='H1',quantity='voltage',location='POC',fundamental_rms=230,source_reference='Synthetic measured spectrum',harmonics=[{'order':3,'rms':4.6},{'order':5,'rms':2.3}])
    assert harmonic_thd(spectrum)==pytest.approx(5**.5)
    p=Project(name='THD',delivery=Delivery(design=Design(harmonic_studies=[spectrum])))
    a=Assessment(id='A1',kind='voltage_thd_pct',location='POC',calculation_id='H1')
    assert assessment_value(p,a)==pytest.approx(5**.5)
    a.kind='current_thd_pct'
    with pytest.raises(ValueError,match='quantity/type mismatch'):assessment_value(p,a)
    with pytest.raises(ValueError):harmonic_thd(HarmonicStudy(id='Empty'))


def test_json_import_validation_fills_optional_arrays_without_saving_project(client):
    response=client.post('/api/delivery/validate',json={'connection_point':'POC'})
    assert response.status_code==200
    assert response.json()['harmonic_studies']==[]
    assert response.json()['policy']['status']=='unverified'
    assert client.get('/api/projects').json()==[]
    assert client.post('/api/delivery/validate',json={'unknown_command':'do something'}).status_code==422
