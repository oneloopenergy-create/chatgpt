"""Immutable scoped releases: design submission must not wait for site commissioning."""
import hashlib
import io
import json
import uuid
import zipfile
from .model import Release
from .readiness import DESIGN_DOCS,COMMISSION_DOCS,workflow,design_hash,accepted,BOUND_EVIDENCE
from .storage import get_blob,put_blob
from ..core.model import now

SCOPES={
 'design':('pre_submission',DESIGN_DOCS,{'standard','cec_certificate','site_survey','msb_declaration','temperature_rise','discrimination','pq_study','pq_allocation','fault_study','annex_h_assessment','backstop_exemption','interface_exemption','alternative_failsafe'}),
 'commissioning':('commissioning',DESIGN_DOCS+COMMISSION_DOCS,{'connection_offer','approved_drawings','approved_settings','capability_test','scada_test','secondary_injection','approved_test_plan','witness_test','primary_antiislanding','msb_declaration'}),
 'handover':('energisation',DESIGN_DOCS+COMMISSION_DOCS, None),
}


def build(p,store,scope,mode,actor):
    if scope not in SCOPES:raise ValueError('Unknown release scope')
    stage,names,kinds=SCOPES[scope]
    row=next(s for s in workflow(p) if s['id']==stage)
    if mode=='final' and row['blockers']:raise ValueError('; '.join(row['blockers']))
    files={};manifest={'project_id':p.id,'project':p.name,'scope':scope,'mode':mode,'design_hash':design_hash(p),'created_by':actor,'created_at':now(),'stage_blockers':row['blockers'],'documents':[],'evidence':[],'disclaimer':'Prepared by GridEasy; portal submission and authoritative signatures/approvals remain external. Generated templates are not issued certificates.'}
    manifest['signoffs']=[s.model_dump(mode='json') for s in p.signoffs]
    manifest['stage_records']=[s.model_dump(mode='json') for s in p.delivery.transitions]
    manifest['stage_status']=workflow(p)
    prefix='DRAFT_' if mode=='draft' else ''
    for name in names:
        doc=p.documents.get(name)
        if not doc:
            if mode=='final':raise ValueError(f'Missing document: {name}')
            continue
        path='drawings-and-design/'+prefix+doc.filename
        files[path]=doc.content.encode()
        manifest['documents'].append({'id':name,'path':path,'sha256':doc.sha256,'signed':p.is_signed(name),'inputs':doc.inputs,'todo':doc.todo})
    for e in p.delivery.evidence:
        if kinds is not None and e.kind not in kinds:continue
        if mode=='final' and not accepted(p,evidence_id=e.id):continue
        try:content=get_blob(store,p.id,e.sha256)
        except (FileNotFoundError,ValueError):raise ValueError(f'Original attachment missing or damaged: {e.filename}')
        path=f'evidence/{e.id}_{e.filename}'
        files[path]=content;manifest['evidence'].append(e.model_dump(mode='json')|{'path':path})
    files['engineering-design.json']=p.delivery.design.model_dump_json(indent=2).encode()
    files['manifest.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
    data=buf.getvalue();digest=put_blob(store,p.id,data,kind='releases')
    release=Release(id=uuid.uuid4().hex[:16],scope=scope+':'+mode,created_at=manifest['created_at'],created_by=actor,design_hash=design_hash(p),sha256=digest,files=list(files))
    p.delivery.releases.append(release);p.log(actor,'delivery.release',release_id=release.id,sha256=digest,scope=scope,mode=mode)
    return release
