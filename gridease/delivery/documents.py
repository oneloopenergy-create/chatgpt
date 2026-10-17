"""Project-specific engineering drawings and reviewable, printable technical records."""
from __future__ import annotations
import csv
import io
from html import escape
from ..core.model import Document
from .readiness import design_issues, protection_issues, control_issues, design_hash, DESIGN_DOCS


def inputs(p):
    return {k:v.version for k,v in p.params.items()} | {'delivery.design':p.params['delivery.design'].version if 'delivery.design' in p.params else 0}


def text(value):
    return 'TBC' if value is None or value=='' else str(value)


def html_doc(p,doc_id,title,filename,sections,todo=None,signed=True):
    body=''.join(f'<h2>{escape(name)}</h2>{content}' for name,content in sections)
    content=f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>{escape(title)}</title>
<style>body{{font:13px/1.6 Arial,sans-serif;margin:32px;color:#20242b}}h1{{font-size:25px}}h2{{font-size:17px;margin-top:28px}}table{{width:100%;border-collapse:collapse}}th,td{{border:1px solid #cbd0d8;padding:7px;text-align:left;overflow-wrap:anywhere}}th{{background:#f4f6fa}}.draft{{color:#b22;font-weight:bold}}.meta{{color:#667}}@media print{{body{{margin:10mm}}tr{{break-inside:avoid}}}}</style>
<p class="draft">DRAFT — ENGINEER REVIEW REQUIRED — NOT A SIGNED CERTIFICATE OR DNSP APPROVAL</p>
<h1>{escape(title)}</h1><p>{escape(p.name)}</p><p class="meta">Project {escape(p.id)} · Design {design_hash(p)[:16]} · Revision {escape(p.delivery.design.drawing_revision or 'TBC')} · Designer {escape(p.delivery.design.responsible_designer or 'TBC')} · Contact {escape(p.delivery.design.designer_contact or 'TBC')}</p>{body}
<h2>Review / external execution</h2><p>Prepared from entered project records. Verify sources, settings, topology and attachments. Responsible person: __________________ Registration / qualification: __________________ Date: __________</p></html>'''
    return Document(doc_id=doc_id,title=title,filename=filename,content=content,content_type='text/html',inputs=inputs(p),todo=todo or [],requires_signoff=signed)


def table(headers,rows):
    return '<table><thead><tr>'+''.join(f'<th>{escape(h)}</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{escape(text(c))}</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table>'


def engineering_sld(p):
    from ..sld.generator import _Svg
    d=p.delivery.design;s=_Svg()
    assets={'GRID':('grid','DNSP network',p.get('site.dnsp','TBC')),'POC':('poc','Connection point',d.connection_point),d.msb_id:('bus','Main switchboard',d.msb_id),d.eg_bus_id:('bus','Generation bus',d.eg_bus_id)}
    for b in d.breakers:assets[b.id]=('breaker',f'{b.id} · {b.role}',f'{text(b.rating_a)} A / {text(b.breaking_ka)} kA · {b.poles}P')
    for t in d.transformers:assets[t.id]=('transformer',t.id,f'{text(t.rating_kva)} kVA · {text(t.primary_v)}/{text(t.secondary_v)} V')
    for e in d.equipment:assets[e.id]=('equipment',f'{e.id} · {e.qty} × {e.kind.upper()}',f'{e.manufacturer} {e.model}')
    # Directed user-entered connectivity controls the layout; there is no invented
    # link from a named breaker to a bus or generator.
    alias={node:t.id for t in d.transformers for node in (t.primary_node,t.secondary_node) if node}
    edges=[(alias.get(c.from_id,c.from_id),alias.get(c.to_id,c.to_id)) for c in d.cables]
    levels={'GRID':0,'POC':1}
    for _ in range(len(assets)):
        changed=False
        for a,b in edges:
            if a in levels and b not in levels:
                levels[b]=levels[a]+1;changed=True
        if not changed:break
    for key in assets:
        if key not in levels:levels[key]=max(levels.values(),default=1)+1
    columns={}
    for key in assets:columns.setdefault(levels[key],[]).append(key)
    width=max(1100,240*(max(columns)+1)+100)
    pos={key:(120+240*col,145+180*i) for col,keys in columns.items() for i,key in enumerate(keys)}
    diagram_bottom=max(y for x,y in pos.values())+130
    s.text(30,30,f'{p.name} — electrical single line diagram',size=20,anchor='start',weight='bold')
    s.text(30,55,f'Rev {d.drawing_revision or "TBC"} · {d.responsible_designer or "designer TBC"} · {d.designer_contact or "contact TBC"} · POC: {d.connection_point or "TBC"} · Ownership: {d.ownership_boundary or "TBC"}',anchor='start')
    for c in d.cables:
        a=alias.get(c.from_id,c.from_id);b=alias.get(c.to_id,c.to_id)
        if a not in pos or b not in pos:continue
        x1,y1=pos[a];x2,y2=pos[b]
        mid=(x1+x2)/2
        s.line(x1+70,y1,mid,y1);s.line(mid,y1,mid,y2);s.line(mid,y2,x2-70,y2)
        s.text(mid,y1-10,c.id,size=10)
    for key,(kind,title,sub) in assets.items():
        x,y=pos[key]
        if kind=='breaker':
            s.rect(x-15,y-15,30,30);s.line(x-15,y-15,x+15,y+15)
            b=next(b for b in d.breakers if b.id==key)
            s.text(x,y+55,f'{b.trip_coil} coil {text(b.coil_voltage_v)} V',size=9)
        elif kind=='transformer':
            s.circle(x-10,y,20);s.circle(x+10,y,20)
            t=next(t for t in d.transformers if t.id==key)
            s.text(x,y+55,f'Z={text(t.impedance_pct)}% · {t.vector_group or "vector TBC"}',size=10)
        elif kind=='bus':s.line(x-65,y,x+65,y,w=6)
        else:s.box(x,y-26,140,52,title,sub,fill='#eef4ff' if kind in ('grid','poc') else '#fff')
        if kind in ('breaker','transformer','bus'):
            s.text(x,y-30,title,size=11,weight='bold');s.text(x,y+38,sub,size=9)
        if kind=='equipment':
            e=next(e for e in d.equipment if e.id==key)
            s.text(x,y+45,f'{text(e.rated_kva)} kVA / {text(e.rated_kw)} kW per unit',size=10)
            s.text(x,y+62,f'CEC: {e.cec_reference or "TBC"}',size=9)
    y=diagram_bottom
    s.text(30,y,'Cable schedule — actual endpoints and installation specification',size=14,anchor='start',weight='bold');y+=25
    for c in d.cables:
        s.text(30,y,f'{c.id}: {c.from_id} → {c.to_id} · {c.cores or "cores TBC"} · {text(c.size_mm2)} mm² {c.material} · {text(c.length_m)} m · {c.installation or "installation TBC"} · Iz {text(c.current_capacity_a)} A',anchor='start');y+=22
    y+=20;s.text(30,y,'CT / VT installation and secondary configuration',size=14,anchor='start',weight='bold');y+=25
    for i in d.instruments:
        s.text(30,y,f'{i.id} {i.kind} · at {i.location_id} · {i.purpose} · {text(i.ratio_primary)}/{text(i.ratio_secondary)} · class {i.accuracy_class or "TBC"} · {text(i.burden_va)} VA',anchor='start');y+=20
        s.text(50,y,f'{i.phases} · {i.winding or "winding TBC"} · terminals {i.secondary_terminals or "TBC"} → {i.relay_input or "meter / TBC"} · earth {i.earthing or "TBC"}',size=10,anchor='start');y+=24
        if i.location_id in pos:
            x,yy=pos[i.location_id];s.circle(x+55,yy-10,9);s.text(x+80,yy-12,i.id,size=9,anchor='start')
    s.line(30,85,width-30,85,dash='6,4');s.text(width-30,75,f'Boundary: {d.ownership_boundary or "UNCONFIRMED"}',anchor='end',size=10)
    s.text(30,y+20,'DRAFT — SUBJECT TO ENGINEER REVIEW AND SIGN-OFF — NOT FOR CONSTRUCTION',anchor='start',fill='#b00',weight='bold')
    s.text(30,y+43,f'Design {design_hash(p)[:16]} · cable graph shown as entered; unconnected items require resolution',anchor='start',size=10)
    return s.render(width,y+65),inputs(p),design_issues(p)


def protection_schematic(p):
    from ..sld.generator import _Svg
    d=p.delivery.design;s=_Svg();width=1400
    s.text(30,30,'Three-phase protection secondary schematic and trip outputs',size=19,anchor='start',weight='bold')
    s.text(30,55,f'{p.name} · Rev {d.drawing_revision or "TBC"} · {d.responsible_designer or "Designer TBC"} · {d.designer_contact or "Contact TBC"}',anchor='start')
    y=100;todo=protection_issues(p)
    for i in d.instruments:
        if i.purpose=='metering':continue
        s.text(30,y,f'{i.id} {i.kind} at {i.location_id} · {text(i.ratio_primary)}/{text(i.ratio_secondary)} · class {i.accuracy_class} · {i.winding}',anchor='start',weight='bold');y+=35
        if not i.circuits:todo.append(f'{i.id}: phase-by-phase terminal wiring not entered')
        for c in i.circuits:
            s.text(30,y+4,f'{i.id} / {c.phase}',anchor='start',size=10)
            s.circle(195,y+12,20)
            if i.kind=='CT':
                s.line(140,y+12,250,y+12,w=2)
                s.text(145,y-17,f'Primary {c.phase}',anchor='start',size=9)
            else:
                s.circle(165,y+12,20)
                s.text(145,y-18,'HV VT primary',anchor='start',size=9)
                if c.phase=='NVD':
                    s.line(135,y+48,150,y+26);s.line(150,y+26,165,y+48);s.line(165,y+48,142,y+48)
                    s.text(120,y+65,'Broken delta terminals per entered winding',anchor='start',size=8)
            # Separate forward and return conductors with explicitly entered terminals.
            s.line(210,y,330,y,w=1.3);s.line(210,y+28,330,y+28,w=1.3)
            s.text(255,y-8,c.secondary_s1 or 'S1 TBC',size=9)
            s.text(255,y+44,c.secondary_s2 or 'S2 TBC',size=9)
            s.rect(330,y-8,160,48,fill='#f8fafc')
            s.text(410,y+8,c.test_input or 'Test input TBC',size=9)
            s.text(410,y+29,c.test_return or 'Test return TBC',size=9)
            s.line(490,y,760,y,w=1.3);s.line(490,y+28,760,y+28,w=1.3)
            s.rect(760,y-12,390,58,fill='#eef4ff')
            s.text(780,y+7,f'{d.relay_id}: {c.relay_input or "input TBC"}',anchor='start',size=10)
            s.text(780,y+30,f'Return: {c.relay_return or "TBC"}',anchor='start',size=10)
            if c.earth_terminal:
                s.line(610,y+28,610,y+56,w=1);s.line(597,y+56,623,y+56,w=1);s.line(601,y+60,619,y+60,w=1);s.line(606,y+64,614,y+64,w=1)
                s.text(635,y+58,c.earth_terminal,anchor='start',size=9)
            y+=100
        y+=20
    s.text(30,y,'Relay element → physical output contact → trip circuit',anchor='start',weight='bold',size=14);y+=40
    for f in d.protection:
        s.text(30,y,f'{f.id} ANSI {f.ansi} · {f.applicability}',anchor='start',size=11,weight='bold')
        if f.applicability!='required':y+=35;continue
        targets=[b for b in d.breakers if b.id in f.target_breakers]
        if not targets:todo.append(f'{f.id}: no declared physical trip device')
        for b in targets:
            s.rect(330,y-20,160,42,fill='#eef4ff');s.text(410,y-3,f'{f.output_contact or "OUT TBC"} · {f.output_mode}',size=10);s.text(410,y+12,f'{f.terminal or "terminal TBC"} / {f.output_test_link or "test link TBC"}',size=9)
            s.text(505,y-28,f'Supply {b.coil_supply or "TBC"} / {text(b.coil_voltage_v)} V',anchor='start',size=9)
            s.line(490,y-4,760,y-4,w=1.3);s.line(490,y+18,760,y+18,w=1.3)
            s.rect(760,y-22,390,48,fill='#fff4ef');s.text(955,y-3,f'{b.id}: {b.trip_coil} release',size=10);s.text(955,y+15,b.coil_terminal or 'Coil terminal TBC',size=9)
            s.line(1150,y+18,1240,y+18,w=1,dash='4,3');s.text(1240,y+35,b.feedback_terminal or 'Feedback TBC',size=9)
            y+=75
    s.text(30,y+20,'Conductor routes are drawn only from declared phase terminal mappings; verify contact polarity, test-link hardware and manufacturer terminal diagrams.',anchor='start',size=10)
    s.text(30,y+42,'DRAFT — REVIEW AND SIGN-OFF REQUIRED — NOT A PERFORMED TEST OR APPROVED CONSTRUCTION DRAWING',anchor='start',fill='#b00',weight='bold')
    return Document(doc_id='protection_schematic',title='Three-phase protection schematic',filename='09_three_phase_protection.svg',content=s.render(width,max(400,y+65)),content_type='image/svg+xml',inputs=inputs(p),todo=todo,requires_signoff=True)


def tripping_matrix(p):
    d=p.delivery.design;buf=io.StringIO();w=csv.writer(buf)
    w.writerow(['DRAFT — engineer-reviewed applicability and approved settings required'])
    w.writerow(['ID','ANSI','Function','Applicability','Applicability basis','Relay input','Output contact','Output behaviour','Output test link','Local indication','Terminal','Threshold','Unit','Delay s','Trip targets','Failure behaviour','Setting source','Approved evidence'])
    for f in d.protection:w.writerow([f.id,f.ansi,f.name,f.applicability,f.applicability_basis,f.relay_input,f.output_contact,f.output_mode,f.output_test_link,f.local_indication,f.terminal,text(f.setting),f.setting_unit,text(f.delay_s),','.join(f.target_breakers),f.fail_safe,f.setting_source,f.approved_evidence_id])
    return Document(doc_id='tripping_matrix',title='Protection tripping matrix',filename='10_tripping_matrix.csv',content=buf.getvalue(),content_type='text/csv',inputs=inputs(p),todo=protection_issues(p),requires_signoff=True)


def site_layout(p):
    from ..sld.generator import _Svg
    d=p.delivery.design;s=_Svg();todo=[]
    if not d.site_survey_reference or not d.site_coordinates_verified_by:todo.append('Verified survey reference and coordinate reviewer required')
    if not d.site_items:todo.append('Site geometry is missing; no physical locations may be inferred')
    minx=min((i.x_m for i in d.site_items),default=0);miny=min((i.y_m for i in d.site_items),default=0)
    spanx=max((i.x_m+i.width_m for i in d.site_items),default=20)-minx
    spany=max((i.y_m+i.height_m for i in d.site_items),default=20)-miny
    scale=min(900/max(spanx,1),600/max(spany,1),25)
    positions={i.id:(60+(i.x_m-minx)*scale,100+(i.y_m-miny)*scale) for i in d.site_items}
    s.text(30,30,f'{p.name} — site layout / cable routes',size=19,anchor='start',weight='bold')
    s.text(30,55,f'Rev {d.drawing_revision or "TBC"} · Designer {d.responsible_designer or "TBC"} · Survey: {d.site_survey_reference or "UNVERIFIED"} · north bearing {d.site_north_deg}° · diagram scale {scale:.2f} px/m',anchor='start',size=10)
    for i in d.site_items:
        x,y=positions[i.id];s.rect(x,y,i.width_m*scale,i.height_m*scale,fill='#eef4ff' if i.kind!='boundary' else '#fff8eb')
        s.text(x+4,y+14,f'{i.id} {i.label or i.kind}',anchor='start',size=10)
        s.text(x+4,y+28,f'({i.x_m:g}, {i.y_m:g}) m',anchor='start',size=9)
    for route in d.site_routes:
        points=[positions[k] for k in route.item_ids if k in positions]
        if len(points)!=len(route.item_ids) or len(points)<2:todo.append(f'{route.id}: route requires at least two declared site items')
        for a,b in zip(points,points[1:]):s.line(*a,*b,w=2,dash='6,3')
        if points:s.text(points[0][0],points[0][1]-8,f'{route.id} / {route.cable_id}',size=9,anchor='start')
    kinds={i.kind for i in d.site_items}
    for kind in ('connection','boundary','switchboard','access'):
        if kind not in kinds:todo.append(f'Site {kind} geometry missing')
    for e in d.equipment:
        if not any(e.id in i.equipment_ids for i in d.site_items):todo.append(f'{e.id}: physical site location missing')
    if d.cables and not d.site_routes:todo.append('Cable routes missing')
    height=max(400,160+spany*scale)
    s.text(30,height-45,'DRAFT — coordinates and dimensions must be checked against the verified survey; not a cadastral survey.',anchor='start',fill='#b00',size=11)
    return Document(doc_id='site_layout',title='Site location and equipment layout',filename='11_site_layout.svg',content=s.render(1100,height),content_type='image/svg+xml',inputs=inputs(p),todo=todo,requires_signoff=True)


def control_description(p):
    c=p.delivery.design.control;todo=control_issues(p)
    keys=['controller','measurement_ct','soft_limit_kw','hard_limit_kw','response_s','response_source','communication_protocol','loss_of_comms_action','loss_of_power_action','watchdog_action','trip_breaker_ids','independent_trip_path','recovery_interlock']
    for k in keys:
        if getattr(c,k) in (None,'',[]):todo.append(f'Control {k} missing')
    if c.soft_limit_kw is not None and c.hard_limit_kw is not None and c.soft_limit_kw>c.hard_limit_kw:todo.append('Soft export limit must not exceed hard trip limit')
    if c.soft_limit_kw is not None and p.get('export.requested_kw') is not None and c.soft_limit_kw>p.get('export.requested_kw'):todo.append('Soft export limit exceeds requested project export')
    return html_doc(p,'control_description','Control description & fail-safe statement','12_control_and_failsafe.html',[
        ('Project-specific controls',table(['Item','Entered design'],[(k,text(getattr(c,k))) for k in keys])),
        ('Loss of communication / power / watchdog',table(['Failure','Action','Trip target','Response / source'],[(name,action,', '.join(c.trip_breaker_ids),f'{text(c.response_s)} s / {c.response_source}') for name,action in [('Communication',c.loss_of_comms_action),('Controller power',c.loss_of_power_action),('Watchdog',c.watchdog_action)]])),
        ('Verification','<p>Demonstrate the entered failure behaviour and restoration interlock in witnessed commissioning tests. No universal 5–15 second default is assumed.</p>')],todo)


def msb_statement(p):
    m=p.delivery.design.msb;policy=p.delivery.design.policy;todo=[]
    if policy.msb_declaration=='unresolved' or not policy.msb_basis:todo.append('Engineer must establish MSB declaration applicability from the relevant source')
    if policy.msb_declaration=='required':
        for k in ('manufacturer','assembly_id','rating_a','short_time_ka','duration_s','prospective_fault_ka','temperature_rise_reference','discrimination_reference','standard_edition'):
            if getattr(m,k) in (None,''):todo.append(f'MSB {k} required')
        if m.short_time_ka and m.prospective_fault_ka and m.duration_s==1 and m.short_time_ka<m.prospective_fault_ka:todo.append('Declared 1 s short-time withstand is below entered prospective fault level')
    return html_doc(p,'msb_statement','MSB manufacturer declaration — preparation template','13_msb_declaration_template.html',[
        ('Applicability',table(['Decision','Basis'],[(policy.msb_declaration,policy.msb_basis)])),
        ('Assembly design record',table(['Field','Entered value'],list(m.model_dump().items()))),
        ('Manufacturer execution','<p>This is a preparation template, not an issued AS/NZS 61439 certificate. Attach the manufacturer-executed declaration, temperature-rise verification and discrimination study. Signatory: __________ Position: __________ Signature: __________ Date: __________</p>')],todo)


def technical_review(p):
    d=p.delivery.design;todo=[];rows=[]
    kinds={'voltage_thd_pct','current_thd_pct','flicker_pst','flicker_plt','voltage_change_pct','fault_ka','discrimination'}
    for kind in kinds:
        if not any(a.kind==kind for a in d.assessments):todo.append(f'Missing {kind} assessment')
    for a in d.assessments:
        from .calculations import assessment_value
        try:result=assessment_value(p,a)
        except ValueError as e:result=None;todo.append(str(e))
        ok=result is not None and a.upper_limit is not None and result<=a.upper_limit
        rows.append([a.id,a.kind,a.location,text(result),text(a.upper_limit),'within entered limit' if ok else 'NOT VERIFIED / EXCEEDS LIMIT',a.method,a.limit_source,a.evidence_id,a.reviewer])
        if not ok or not all((a.method,a.limit_source,a.evidence_id,a.reviewer)):todo.append(f'{a.id}: complete sourced study / review required')
    return html_doc(p,'technical_review','Power quality, fault level & discrimination review','14_technical_review.html',[
        ('Harmonic calculation method','<p>For a linked spectrum, THD = 100 × sqrt(sum(RMS(h)^2, h ≥ 2)) / fundamental RMS. Only the entered spectrum is evaluated; unmeasured orders, background network distortion and frequency transfer are not inferred. Customer emission allocation and external study review remain required.</p>'),
        ('Study results',table(['ID','Study','Location','Result','Limit','Comparison','Method','Limit source','Report evidence','Reviewer'],rows)),
        ('Limitations','<p>THD, flicker, fault level and coordination require real studies and sourced limits. Empty results do not pass. Comparison against an entered limit is not a DNSP approval. The separate OpenDSS study covers only its explicit model and operating point.</p>')],todo)


def application_schedule(p):
    from .readiness import design_issues,protection_issues
    d=p.delivery.design
    return html_doc(p,'application_schedule','DNSP design information pack / manual submission schedule','15_application_schedule.html',[
        ('Application',table(['Field','Project value'],[(k,p.get(k)) for k in ('site.customer','site.address','site.nmi','site.dnsp','generation.max_kw','connection.supply_voltage_v','export.requested_kw')])),
        ('Source profile',table(['Field','Value'],list(d.policy.model_dump(mode='json').items()))),
        ('Deliverable index',table(['Document ID','Filename'],[(k,p.documents[k].filename if k in p.documents else 'NOT GENERATED') for k in DESIGN_DOCS])),
        ('Manual portal action','<p>An employee must use the relevant official DNSP portal, confirm the current application path and required official forms, then upload this reviewed package. This software does not submit, pay or accept an offer on your behalf. The schedule supplements rather than impersonates an official DNSP form.</p>')],design_issues(p)+protection_issues(p))


def commissioning_plan(p):
    d=p.delivery.design
    rows=[]
    for f in d.protection:
        if f.applicability=='required':
            for target in f.target_breakers:rows.append([f.id,f.ansi,target,text(f.setting),f.setting_unit,text(f.delay_s),f.approved_evidence_id])
    return html_doc(p,'commissioning_plan','Construction, communications & secondary injection test plan','16_commissioning_plan.html',[
        ('Approved protection test schedule',table(['Function','ANSI','Trip target','Setting','Unit','Approved time s','Approved settings evidence'],rows)),
        ('Communications',table(['Item','Design'],list(d.control.model_dump().items()))),
        ('Test execution','<p>Qualified personnel must use calibrated instruments and approved isolation procedures. Record each protection function and trip target, measured operating time, observed trip and restoration interlock. Complete OEM capability/backstop or RTU/SCADA tests according to the reviewed applicability profile. Do not treat a generated plan as a performed test.</p>')],protection_issues(p),signed=True)


def secondary_report(p):
    d=p.delivery.design;rows=[];todo=[]
    for f in d.protection:
        if f.applicability=='required':
            for target in f.target_breakers:
                if not any(t.kind=='secondary_injection' and t.function_id==f.id and t.target_breaker==target for t in d.tests):todo.append(f'{f.id} → {target}: test not recorded')
    for t in d.tests:
        if t.kind!='secondary_injection':continue
        rows.append([t.id,t.function_id,t.target_breaker,text(t.injection_value),text(t.measured_pickup),t.unit,text(t.measured_time_s),text(t.maximum_time_s),str(t.trip_observed),t.outcome,t.operator,t.qualification,t.calibration_reference,t.evidence_id])
        if t.outcome!='pass' or t.trip_observed is not True or t.measured_time_s is None or t.maximum_time_s is None or t.measured_time_s>t.maximum_time_s:todo.append(f'{t.id}: incomplete or failed measurement')
    return html_doc(p,'secondary_injection_report','Secondary injection test record — entered measurements','17_secondary_injection_record.html',[
        ('Recorded results',table(['Test','Function','Target','Injection','Measured pickup','Unit','Measured s','Maximum s','Trip seen','Result','Operator','Qualification','Calibration','Signed evidence'],rows)),
        ('Execution','<p>This report reproduces entered measurements. Attach the qualified tester’s signed report and calibration evidence; generating this document does not perform or certify a physical test.</p>')],todo,signed=False)


def communications_report(p):
    d=p.delivery.design;tests=[t for t in d.tests if t.kind in ('communications','backstop','interlock')]
    return html_doc(p,'communications_report','Communications / backstop / fail-safe test record','18_communications_record.html',[
        ('Applicable interface',table(['Mode','Basis','Protocol','RTU','OEM'],[(d.policy.communication_mode,d.policy.communication_basis,d.control.communication_protocol,d.control.rtu_model,d.control.oem_client)])),
        ('Recorded tests',table(['Test','Type','Result','Operator','Date','Evidence'],[(t.id,t.kind,t.outcome,t.operator,t.performed_on,t.evidence_id) for t in tests]))],[] if tests and all(t.outcome=='pass' for t in tests) else ['Communications and fail-safe physical tests are not completed'],signed=False)


def handover_register(p):
    d=p.delivery.design
    return html_doc(p,'handover_register','Offer, commissioning, CCEW & energisation register','19_handover_register.html',[
        ('Milestones',table(['Field','Recorded value'],list(d.milestones.model_dump(mode='json').items()))),
        ('Evidence register',table(['ID','Type','Filename','Issuer','Reference','Status','Reviewer','SHA-256'],[(e.id,e.kind,e.filename,e.issuer,e.reference,e.status,e.reviewed_by,e.sha256) for e in p.delivery.evidence])),
        ('Responsibility','<p>Only the DNSP and other responsible issuers can issue offers, numbers and energisation permissions. This register records them; no ID or permission is generated by GridEasy.</p>')],signed=False)


GENERATORS={
    'protection_schematic':protection_schematic,'tripping_matrix':tripping_matrix,'site_layout':site_layout,
    'control_description':control_description,'msb_statement':msb_statement,'technical_review':technical_review,
    'application_schedule':application_schedule,'commissioning_plan':commissioning_plan,
    'secondary_injection_report':secondary_report,'communications_report':communications_report,'handover_register':handover_register,
}
