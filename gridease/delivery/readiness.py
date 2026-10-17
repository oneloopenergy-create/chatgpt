"""Seven-stage checks distinguish generated drafts from external signed evidence."""
from __future__ import annotations
from datetime import date
import hashlib
import json

from .model import Transition
from ..core.model import now

DESIGN_DOCS = ['sld','protection_schematic','tripping_matrix','site_layout','control_description','msb_statement','technical_review','application_schedule']
COMMISSION_DOCS = ['commissioning_plan','secondary_injection_report','communications_report','handover_register']
STAGES = [
    ('sld','1 · 单线图与工程拓扑'), ('design_pack','2 · 配套设计图纸与技术包'),
    ('pre_submission','3 · 递交前合规初审'), ('submission','4 · 人工递交与技术评估'),
    ('offer','5 · 并网协议与工程编号'), ('commissioning','6 · 安装、通信与二次注入'),
    ('energisation','7 · 验收、CCEW 与授权送电'),
]
BOUND_EVIDENCE = {'cec_certificate','site_survey','msb_declaration','temperature_rise','discrimination','pq_study','fault_study','approved_drawings','approved_settings','capability_test','scada_test','secondary_injection','ccew','inspection','permission_to_connect','pq_allocation','alternative_failsafe','interface_exemption','approved_test_plan','witness_test','primary_antiislanding','backstop_exemption','annex_h_assessment'}


def design_hash(p):
    if p.delivery is None:
        return ''
    values = {k: v.value for k,v in p.params.items() if not k.startswith(('delivery.', 'calc.bess_'))}
    return hashlib.sha256(json.dumps({'engineering':p.delivery.design.fingerprint(),'parameters':values},sort_keys=True,default=str).encode()).hexdigest()


def stage_hash(p, stage):
    d=p.delivery.design
    extra={}
    if stage in ('submission','offer','commissioning','energisation'):
        fields={'submission':['submission_reference','submitted_on','submitted_by'],
                'offer':['offer_reference','accepted_on','payment_reference','job_number','der_register_number'],
                'commissioning':[],
                'energisation':['inspection_booking','inspection_on','permission_reference','energised_on']}[stage]
        values=d.milestones.model_dump(mode='json')
        extra['milestones']={k:values[k] for k in fields}
    if stage in ('commissioning','energisation'):
        extra['tests']=[t.model_dump(mode='json') for t in d.tests]
    return hashlib.sha256(json.dumps([design_hash(p),extra],sort_keys=True).encode()).hexdigest()


def accepted(p, kind=None, evidence_id=None):
    if p.delivery is None:return False
    for e in p.delivery.evidence:
        if kind and e.kind != kind:continue
        if evidence_id and e.id != evidence_id:continue
        if e.status!='accepted' or not e.reviewed_by or not e.issuer or not e.reference:continue
        if e.kind in BOUND_EVIDENCE and e.design_hash!=design_hash(p):continue
        return True
    return False


def design_issues(p):
    if p.delivery is None:return ['Enable the engineering delivery workspace']
    d=p.delivery.design; out=[]
    def need(value,msg):
        if value is None or value=='' or value==[]:out.append(msg)
    need(d.connection_point,'Connection point / point of supply is missing')
    need(d.ownership_boundary,'Physical ownership boundary is missing')
    need(d.breakers,'Breaker and isolation schedule is missing')
    roles={b.role for b in d.breakers}
    for role in ('incomer','eg_common','isolation'):
        if role not in roles:out.append(f'Missing {role} breaker / isolation point')
    ids={b.id for b in d.breakers}|{t.id for t in d.transformers}|{e.id for e in d.equipment}|{d.msb_id,d.eg_bus_id,'GRID','POC',d.relay_id}|{v for t in d.transformers for v in (t.primary_node,t.secondary_node) if v}
    for b in d.breakers:
        for val,label in ((b.rating_a,'rated current'),(b.breaking_ka,'breaking capacity'),(b.location,'location')):need(val,f'{b.id}: {label} missing')
        if b.role=='eg_common':
            if b.trip_coil in ('unknown','none'):out.append(f'{b.id}: controlled trip coil required')
            for val,label in ((b.coil_voltage_v,'coil voltage'),(b.coil_supply,'coil supply'),(b.coil_terminal,'trip terminal'),(b.feedback_terminal,'feedback terminal')):need(val,f'{b.id}: {label} missing')
    if (p.get('connection.supply_voltage_v') or 0)>=1000 and not d.transformers:out.append('HV connection requires a transformer schedule')
    for t in d.transformers:
        for k in ('rating_kva','primary_v','secondary_v','impedance_pct','vector_group','source_ref'):need(getattr(t,k),f'{t.id}: {k} missing')
    need(d.cables,'Cable schedule missing')
    for c in d.cables:
        for k in ('from_id','to_id','cores','size_mm2','length_m','installation','current_capacity_a','source_ref'):need(getattr(c,k),f'{c.id}: {k} missing')
        if c.material=='unknown':out.append(f'{c.id}: conductor material missing')
        if c.from_id not in ids or c.to_id not in ids:out.append(f'{c.id}: cable endpoint is not a declared electrical asset')
    # Require actual connectivity, not merely a list of cable labels.
    adjacency={}
    for a,b in [(c.from_id,c.to_id) for c in d.cables]+[(t.primary_node,t.secondary_node) for t in d.transformers if t.primary_node and t.secondary_node]:
        adjacency.setdefault(a,set()).add(b);adjacency.setdefault(b,set()).add(a)
    seen={'GRID'};todo=list(seen)
    while todo:
        node=todo.pop()
        for target in adjacency.get(node,set())-seen:seen.add(target);todo.append(target)
    for node in ['POC',d.msb_id,d.eg_bus_id]+[e.id for e in d.equipment]+[b.id for b in d.breakers]+[t.primary_node or t.id for t in d.transformers]:
        if node not in seen:out.append(f'{node}: no declared cable path to POC/GRID')
    # Every generation path must actually traverse the declared controlled CB.
    common={b.id for b in d.breakers if b.role=='eg_common'}
    reachable={'GRID'}-common;queue=list(reachable)
    while queue:
        node=queue.pop()
        for target in adjacency.get(node,set())-reachable-common:reachable.add(target);queue.append(target)
    if common and any(e.id in reachable for e in d.equipment):out.append('Generation cable path bypasses the EG common coupling breaker')
    need(d.equipment,'Generation equipment schedule missing')
    for e in d.equipment:
        for k in ('manufacturer','model','rated_kva','rated_kw','cec_reference','cec_expiry','branch_cb'):need(getattr(e,k),f'{e.id}: {k} missing')
        if e.cec_expiry and e.cec_expiry<date.today():out.append(f'{e.id}: CEC evidence has expired')
        if e.branch_cb not in {b.id for b in d.breakers}:out.append(f'{e.id}: branch CB is not declared')
        if e.rated_kw and e.rated_kva and e.rated_kw>e.rated_kva:out.append(f'{e.id}: rated kW exceeds kVA')
    for purpose in ('protection','metering'):
        if not any(i.kind=='CT' and i.purpose==purpose for i in d.instruments):out.append(f'{purpose} CT schedule missing')
    for i in d.instruments:
        for k in ('location_id','ratio_primary','ratio_secondary','accuracy_class','winding','secondary_terminals','source_ref'):need(getattr(i,k),f'{i.id}: {k} missing')
        if i.location_id not in ids:out.append(f'{i.id}: installation location is not a declared asset')
        if i.purpose in ('protection','NVD'):
            expected={'NVD'} if i.purpose=='NVD' else {v.strip() for v in i.phases.split(',')}
            if not expected <= {c.phase for c in i.circuits}:out.append(f'{i.id}: explicit phase-by-phase secondary terminal circuits missing')
            for c in i.circuits:
                for key in ('secondary_s1','secondary_s2','test_input','test_return','relay_input','relay_return','earth_terminal'):
                    if not getattr(c,key):out.append(f'{c.id}: {key} missing')
            for k in ('relay_input','earthing','test_block'):need(getattr(i,k),f'{i.id}: {k} missing')
        if i.purpose=='NVD' and i.kind!='VT':out.append(f'{i.id}: NVD winding must be a VT')
    if (p.get('connection.supply_voltage_v') or 0)>=1000 and not any(i.kind=='VT' for i in d.instruments):out.append('HV project requires a declared VT arrangement or engineer-approved project basis')
    return out


def protection_issues(p):
    d=p.delivery.design;out=[];ids={b.id:b for b in d.breakers}
    functions={f.ansi:f for f in d.protection}
    for ansi in d.policy.required_protection_functions:
        if ansi not in functions:out.append(f'{ansi}: applicability has not been assessed')
    for f in d.protection:
        if f.applicability=='unresolved':out.append(f'{f.id}: applicability unresolved')
        if not f.applicability_basis:out.append(f'{f.id}: applicability source required')
        if f.applicability=='not_applicable':continue
        for k in ('relay_model','relay_input','output_contact','terminal','target_breakers','setting_source'):
            if not getattr(f,k):out.append(f'{f.id}: {k} missing')
        if f.delay_s is None:out.append(f'{f.id}: approved operating time missing')
        if f.ansi not in ('watchdog','loss_of_mains') and f.setting is None:out.append(f'{f.id}: operating threshold missing')
        for target in f.target_breakers:
            if target not in ids:out.append(f'{f.id}: unknown trip target {target}')
            elif ids[target].trip_coil in ('none','unknown'):out.append(f'{f.id}: {target} has no defined trip coil')
    return out


def control_issues(p):
    d=p.delivery.design;c=d.control;out=[]
    if c.measurement_ct not in {i.id for i in d.instruments if i.kind=='CT'}:out.append('Export measurement CT is not declared')
    ids={b.id for b in d.breakers}
    if any(b not in ids for b in c.trip_breaker_ids):out.append('Fail-safe targets include an unknown breaker')
    if not any(b.role=='eg_common' and b.id in c.trip_breaker_ids for b in d.breakers):out.append('Fail-safe logic must identify the actual generation coupling disconnect')
    for i in d.instruments:
        if i.purpose=='NVD' and not all(v in i.winding.casefold() for v in ('delta',)):
            out.append(f'{i.id}: NVD winding arrangement must identify its open/broken delta configuration')
    return out


def document_issues(p, names, signed=False):
    out=[];stale=set(p.stale_documents())
    for name in names:
        doc=p.documents.get(name)
        if not doc:out.append(f'Required document missing: {name}');continue
        if name in stale:out.append(f'Document out of date: {name}')
        if doc.todo:out.append(f'{name}: {len(doc.todo)} unresolved review item(s)')
        if signed and doc.requires_signoff and not p.is_signed(name):out.append(f'{name}: engineer review/sign-off missing')
    return out


def stage_issues(p, stage):
    if p.delivery is None:return ['Enable the engineering delivery workspace']
    d=p.delivery.design;out=[];m=d.milestones
    if stage=='sld':return design_issues(p)+document_issues(p,['sld'])
    if stage=='design_pack':
        from .standards import issues as standards_issues
        return protection_issues(p)+control_issues(p)+standards_issues(p)+document_issues(p,DESIGN_DOCS)
    if stage=='pre_submission':
        from .standards import issues as standards_issues
        out+=standards_issues(p)
        out+=document_issues(p,DESIGN_DOCS,signed=True)
        policy=d.policy
        if policy.status!='reviewed' or not all((policy.document_reference,policy.edition,policy.clause,policy.applicability,policy.reviewed_by,policy.reviewed_on)) or not accepted(p,'standard',policy.evidence_id):out.append('Applicable DNSP source/edition/clauses must be reviewed against an accepted source document')
        if policy.dnsp.casefold()!=str(p.get('site.dnsp','')).casefold():out.append('Reviewed requirements profile does not match project DNSP')
        if policy.valid_until and policy.valid_until<date.today():out.append('Requirements profile review has expired')
        if not accepted(p,'cec_certificate'):out.append('Current CEC verification evidence required')
        for e in d.equipment:
            if not accepted(p,'cec_certificate',e.cec_evidence_id):out.append(f'{e.id}: link the reviewed model-specific CEC evidence')
        if not accepted(p,'site_survey'):out.append('Reviewed site survey required')
        if policy.msb_declaration=='unresolved' or not policy.msb_basis:out.append('MSB declaration applicability and source unresolved')
        if policy.msb_declaration=='required':
            for kind in ('msb_declaration','temperature_rise','discrimination'):
                if not accepted(p,kind):out.append(f'Reviewed external evidence required: {kind}')
        required={'voltage_thd_pct','current_thd_pct','flicker_pst','flicker_plt','voltage_change_pct','fault_ka','discrimination'}
        for kind in required:
            rows=[a for a in d.assessments if a.kind==kind]
            if not rows:out.append(f'Engineering assessment missing: {kind}')
            for a in rows:
                from .calculations import assessment_value
                try:result=assessment_value(p,a)
                except ValueError as e:out.append(str(e));continue
                if result is None or a.upper_limit is None or not all((a.method,a.limit_source,a.reviewer)) or not accepted(p,'fault_study' if a.kind=='fault_ka' else 'discrimination' if a.kind=='discrimination' else 'pq_study',a.evidence_id):out.append(f'{a.id}: incomplete assessment/source/reviewed evidence')
                elif result>a.upper_limit:out.append(f'{a.id}: result exceeds sourced limit')
        if p.assumptions():out.append(f'{len(p.assumptions())} assumptions require confirmation')
        from ..compliance.checks import run_checks
        if any(f.severity=='error' for f in run_checks(p)):out.append('Resolve error-level project compliance findings')
        return out
    if stage=='submission':
        if not all((m.submission_reference,m.submitted_on,m.submitted_by)):out.append('Manual portal submission reference/date/employee required')
        if not accepted(p,'submission_receipt'):out.append('Portal submission receipt required')
        if any(not i.resolved for r in p.rfi_rounds for i in r.items):out.append('Open DNSP RFI items remain')
    elif stage=='offer':
        if m.accepted_on and m.submitted_on and m.accepted_on<m.submitted_on:out.append('Offer acceptance cannot precede portal submission')
        if not all((m.offer_reference,m.accepted_on,m.payment_reference,m.job_number,m.der_register_number)):out.append('Offer acceptance/payment/job number/DER register reference required; record actual issuer-assigned identifiers')
        for kind in ('connection_offer','approved_drawings','approved_settings','payment','der_registration'):
            if not accepted(p,kind):out.append(f'Accepted external evidence required: {kind}')
        for f in d.protection:
            if f.applicability=='required' and not accepted(p,'approved_settings',f.approved_evidence_id):out.append(f'{f.id}: setting must link to current DNSP-approved evidence')
    elif stage=='commissioning':
        from .standards import commissioning_issues
        out+=commissioning_issues(p)
        out+=document_issues(p,COMMISSION_DOCS)
        if d.policy.communication_mode=='unresolved' or not d.policy.communication_basis:out.append('CSIP-Aus/SCADA applicability must be sourced and reviewed')
        evidence_kind='capability_test' if d.policy.communication_mode=='CSIP-Aus' else 'scada_test' if d.policy.communication_mode=='SCADA' else 'communications_test'
        if not accepted(p,evidence_kind):out.append(f'Accepted communications evidence required: {evidence_kind}')
        if m.accepted_on and any(t.performed_on and t.performed_on<m.accepted_on for t in d.tests):out.append('Commissioning results cannot predate the recorded accepted offer for this design')
        for kind in ('secondary_injection',):
            if not accepted(p,kind):out.append(f'Accepted external evidence required: {kind}')
        for f in d.protection:
            if f.applicability!='required':continue
            for target in f.target_breakers:
                results=[t for t in d.tests if t.kind=='secondary_injection' and t.function_id==f.id and t.target_breaker==target]
                if not results:out.append(f'{f.id} → {target}: secondary injection result missing')
                for t in results:
                    if d.policy.source_document_id=='NS194-Rev5-20260910':
                        if f.delay_s is not None and t.tolerance_s is not None and t.tolerance_s>f.delay_s*.05+1e-9:out.append(f'[NS194 Annex B] {t.id}: time tolerance exceeds 5% of the entered approved delay')
                        accuracy=.02 if f.ansi in ('27','59') else .01 if f.ansi in ('81U','81O') else None
                        if accuracy is not None and (t.measured_pickup is None or f.setting is None or f.setting<=0 or t.unit!=f.setting_unit or abs(t.measured_pickup-f.setting)>abs(f.setting)*accuracy+1e-9):out.append(f'[NS194 Annex B] {t.id}: measured pickup/unit missing or outside voltage/frequency accuracy limit')
                    if t.outcome!='pass' or t.trip_observed is not True or t.measured_time_s is None or t.maximum_time_s is None or t.measured_time_s>t.maximum_time_s or t.tolerance_s is None or f.delay_s is None or t.maximum_time_s>f.delay_s+(t.tolerance_s or 0)+1e-9 or not t.acceptance_source or not all((t.operator,t.qualification,t.instrument,t.calibration_reference,t.performed_on)) or not accepted(p,'secondary_injection',t.evidence_id):out.append(f'{t.id}: incomplete/failed signed test evidence')
        if not any(t.kind in ('communications','backstop') and t.outcome=='pass' and t.operator and t.performed_on and accepted(p,evidence_kind,t.evidence_id) for t in d.tests):out.append('Completed communication capability/backstop test record required')
        for scenario in ('communication_loss','controller_power_loss','watchdog','recovery_interlock'):
            tests=[t for t in d.tests if t.kind=='interlock' and t.scenario==scenario]
            if not tests or not any(t.outcome=='pass' and t.trip_observed is True and t.operator and t.performed_on and t.measured_time_s is not None and d.control.response_s is not None and t.measured_time_s<=d.control.response_s and accepted(p,evidence_kind,t.evidence_id) for t in tests):out.append(f'Witnessed fail-safe test required: {scenario}')
    elif stage=='energisation':
        if m.energised_on and m.inspection_on and m.energised_on<m.inspection_on:out.append('Permanent energisation cannot predate the recorded final inspection')
        if m.inspection_on and m.accepted_on and m.inspection_on<m.accepted_on:out.append('Final inspection cannot predate the accepted offer')
        if not all((m.inspection_booking,m.inspection_on,m.permission_reference,m.energised_on)):out.append('Inspection booking/date and actual permission/energisation date required')
        for kind in ('ccew','inspection','permission_to_connect'):
            if not accepted(p,kind):out.append(f'Accepted external evidence required: {kind}')
        if any(t.outcome=='fail' for t in d.tests):out.append('Unresolved failed tests prevent energisation')
    return out


def workflow(p):
    result=[];prior_complete=True
    for code,title in STAGES:
        own=list(dict.fromkeys(stage_issues(p,code)))
        blockers=own+([] if prior_complete else ['Complete/revalidate the previous stage first'])
        stamp=next((t for t in reversed(p.delivery.transitions if p.delivery else []) if t.stage==code),None)
        complete=bool(stamp and stamp.design_hash==stage_hash(p,code) and not blockers)
        result.append({'id':code,'title':title,'status':'complete' if complete else ('ready' if not blockers else 'blocked'),'blockers':blockers,'completed_at':stamp.completed_at if complete else None})
        prior_complete=complete
    return result


def complete_stage(p,stage,actor,notes=''):
    row=next((s for s in workflow(p) if s['id']==stage),None)
    if row is None:raise ValueError('Unknown delivery stage')
    if row['blockers']:raise ValueError('; '.join(row['blockers']))
    p.delivery.transitions.append(Transition(stage=stage,completed_at=now(),completed_by=actor,design_hash=stage_hash(p,stage),notes=notes))
    p.log(actor,'delivery.stage.complete',stage=stage,design_hash=design_hash(p))
