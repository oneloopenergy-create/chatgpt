from __future__ import annotations
import base64
import binascii
from datetime import date
from pathlib import PurePath
from urllib.parse import quote
from typing import Literal
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from .model import Design, Delivery, Evidence, EVIDENCE_KINDS
from .readiness import design_hash,workflow,complete_stage,BOUND_EVIDENCE
from .storage import put_blob,get_blob,MAX_FILE_BYTES,ALLOWED_EXTENSIONS
from ..core.model import Project,Source,SourceKind,now


class Action(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True)
    actor:str=Field(min_length=1,max_length=100)
    notes:str=''


class Upload(Action):
    kind:EVIDENCE_KINDS
    filename:str=Field(min_length=1,max_length=180)
    content_base64:str=Field(min_length=1,max_length=MAX_FILE_BYTES*4//3+4)
    issuer:str=Field(min_length=1,max_length=200)
    reference:str=Field(min_length=1,max_length=200)
    issued_on:date | None=None


class Review(Action):
    status:str=Field(pattern='^(accepted|rejected)$')


def register(app,load,store,summary,refresh_design):
    router=APIRouter()

    def enabled(p):
        if p.delivery is None:raise HTTPException(409,'Enable the engineering delivery workspace first')

    @router.get('/api/delivery/schema')
    def schema():
        from typing import get_args
        from .standards import CATALOG
        from ..sld.references import reference_catalog
        return {'design':Design.model_json_schema(),'evidence_kinds':list(get_args(EVIDENCE_KINDS)),'standards':CATALOG,'sld_references':reference_catalog()}

    @router.get('/api/projects/{pid}/delivery/sld-print')
    def sld_print(p:Project=Depends(load)):
        enabled(p)
        doc=p.documents.get('sld')
        if doc is None:raise HTTPException(404,'SLD has not been generated')
        from ..sld.engineering import printable_sld
        return Response(printable_sld(doc.content),media_type='text/html')

    @router.post('/api/delivery/validate')
    def validate_import(body:Design):
        return body.model_dump(mode='json')

    @router.post('/api/projects/{pid}/delivery/activate')
    def activate(body:Action,p:Project=Depends(load),st=Depends(store)):
        if p.delivery is None:
            p.delivery=Delivery()
            p.log(body.actor,'delivery.activate')
            refresh_design(p);st.save(p)
        return summary(p)

    @router.put('/api/projects/{pid}/delivery/design')
    def design(body:Design,p:Project=Depends(load),st=Depends(store),actor:str=Query(default="employee",min_length=1,max_length=100)):
        enabled(p)
        old=p.delivery.design
        p.delivery.design=body
        p.set_param('delivery.design',body.model_dump(mode='json'),Source(kind=SourceKind.USER_INPUT,ref='engineering design form'),actor=actor)
        # Typed equipment and legacy calculations share the same nameplate data.
        if body.equipment or old.equipment:
            for kind,key in [('pv','equipment.pv_inverters'),('bess','equipment.bess')]:
                values=[]
                for e in body.equipment:
                    if e.kind!=kind:continue
                    if e.rated_kva is None or not e.manufacturer or not e.model:
                        raise HTTPException(422,f'{e.id}: manufacturer, model and rated kVA are required')
                    item={'manufacturer':e.manufacturer,'model':e.model,'qty':e.qty,('rated_ac_kva' if kind=='pv' else 'pcs_kva'):e.rated_kva}
                    if e.energy_kwh is not None:item['energy_kwh']=e.energy_kwh
                    if e.dc_kwp is not None:item['dc_kwp']=e.dc_kwp
                    values.append(item)
                p.set_param(key,values,Source(kind=SourceKind.USER_INPUT,ref='engineering equipment schedule'))
        refresh_design(p)
        p.log(actor,'delivery.design.save',design_hash=design_hash(p))
        st.save(p)
        return summary(p)

    @router.get('/api/projects/{pid}/delivery/workflow')
    def stages(p:Project=Depends(load)):
        enabled(p);return workflow(p)

    @router.post('/api/projects/{pid}/delivery/stages/{stage}/complete')
    def complete(stage:str,body:Action,p:Project=Depends(load),st=Depends(store)):
        enabled(p)
        try:complete_stage(p,stage,body.actor,body.notes)
        except ValueError as e:raise HTTPException(409,str(e))
        st.save(p);return summary(p)

    @router.post('/api/projects/{pid}/delivery/evidence',status_code=201)
    def upload(body:Upload,p:Project=Depends(load),st=Depends(store)):
        enabled(p)
        name=body.filename.replace('\\','/').split('/')[-1]
        if PurePath(name).suffix.lower() not in ALLOWED_EXTENSIONS or any(ord(c)<32 or c in '"<>:|?*' for c in name):
            # Files remain attachments; never execute or inline arbitrary uploaded content.
            raise HTTPException(422,'Use a supported document extension and a safe filename')
        try:data=base64.b64decode(body.content_base64,validate=True)
        except (ValueError,binascii.Error):raise HTTPException(422,'Invalid base64 file content')
        if not data or len(data)>MAX_FILE_BYTES:raise HTTPException(413,'File must contain 1 byte to 10 MiB')
        digest=put_blob(st,p.id,data)
        p.delivery.evidence.append(Evidence(id=uuid.uuid4().hex[:16],kind=body.kind,filename=name,sha256=digest,size=len(data),uploaded_at=now(),uploaded_by=body.actor,issuer=body.issuer,reference=body.reference,issued_on=body.issued_on,design_hash=design_hash(p)))
        p.log(body.actor,'evidence.upload',filename=name,kind=body.kind,sha256=digest)
        refresh_design(p);st.save(p);return summary(p)

    @router.post('/api/projects/{pid}/delivery/evidence/{evidence_id}/review')
    def review(evidence_id:str,body:Review,p:Project=Depends(load),st=Depends(store)):
        enabled(p)
        e=next((e for e in p.delivery.evidence if e.id==evidence_id),None)
        if e is None:raise HTTPException(404,'Evidence not found')
        try:get_blob(st,p.id,e.sha256)
        except (FileNotFoundError,ValueError):raise HTTPException(409,'Original evidence file missing or hash invalid')
        if body.status=='accepted' and e.kind in BOUND_EVIDENCE and e.design_hash!=design_hash(p):raise HTTPException(409,'This file belongs to an earlier design. Upload the current issued document for review.')
        if not body.notes.strip():raise HTTPException(422,'Record the review basis and scope')
        e.status=body.status;e.reviewed_by=body.actor;e.reviewed_at=now();e.review_note=body.notes
        p.log(body.actor,'evidence.review',evidence_id=e.id,status=e.status,notes=body.notes)
        refresh_design(p);st.save(p);return summary(p)

    @router.get('/api/projects/{pid}/delivery/evidence/{evidence_id}/download')
    def download(evidence_id:str,p:Project=Depends(load),st=Depends(store)):
        enabled(p);e=next((e for e in p.delivery.evidence if e.id==evidence_id),None)
        if e is None:raise HTTPException(404,'Evidence not found')
        try:content=get_blob(st,p.id,e.sha256)
        except FileNotFoundError:raise HTTPException(404,'Original file missing')
        except ValueError as err:raise HTTPException(409,str(err))
        return Response(content,media_type='application/octet-stream',headers={'Content-Disposition':f"attachment; filename*=UTF-8''{quote(e.filename)}",'X-Content-Type-Options':'nosniff'})

    @router.get('/api/projects/{pid}/delivery/design/export')
    def export(p:Project=Depends(load)):
        enabled(p)
        return Response(p.delivery.design.model_dump_json(indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="engineering-design.json"'})

    @router.post('/api/projects/{pid}/delivery/simulate')
    def simulate(body:Action,p:Project=Depends(load),st=Depends(store)):
        enabled(p)
        from .simulation import solve
        try:p.delivery.simulation=solve(p)
        except (ValueError, RuntimeError) as e:raise HTTPException(422,str(e))
        except Exception as e:
            # Native DSS exceptions carry the engine diagnostic; never turn a failed
            # solve into an empty or "passing" result.
            raise HTTPException(422,f'OpenDSS study failed: {e}')
        p.log(body.actor,'delivery.simulate',run_id=p.delivery.simulation.id)
        st.save(p);return summary(p)

    @router.post('/api/projects/{pid}/delivery/releases')
    def release(body:Action,scope:Literal['design','commissioning','handover']='design',mode:Literal['draft','final']='draft',p:Project=Depends(load),st=Depends(store)):
        enabled(p)
        from .package import build
        try:r=build(p,st,scope,mode,body.actor)
        except ValueError as e:raise HTTPException(409,str(e))
        st.save(p);return {'release':r.model_dump(mode='json'),'project':summary(p)}

    @router.get('/api/projects/{pid}/delivery/releases/{release_id}/download')
    def release_download(release_id:str,p:Project=Depends(load),st=Depends(store)):
        enabled(p);r=next((r for r in p.delivery.releases if r.id==release_id),None)
        if r is None:raise HTTPException(404,'Release not found')
        try:content=get_blob(st,p.id,r.sha256,kind='releases')
        except (FileNotFoundError,ValueError) as e:raise HTTPException(409,str(e))
        return Response(content,media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="GridEasy_{r.scope.replace(":","_")}_{r.id}.zip"'})

    app.include_router(router)
