"""Clause-level checks against identified user-supplied editions, not inferred live currency."""
from __future__ import annotations
import re

CATALOG={
 'NS194-Rev5-20260910':{
  'title':'Ausgrid NS194 Inverter Energy Systems','edition':'Revision 5, approved 2026-09-10',
  'sha256':'3315658d09b929a7c0cacb7ce9e646bf42d47e87df9bfafd57c2bc317dd6a071',
  'currency':'User-supplied copy; latest online edition not independently verified',
  'clauses':{
   '4.1.2':'Total inverter capacity >200 kVA uses interface protection under section 5 and Annex A; residential-cluster exceptions need separate assessment.',
   '5.7.4 / 5.8.2':'Applicable inter-trip communications loss must disconnect within 5 seconds and inhibit reconnection until restoration.',
   '5.9.2':'Shunt trip circuit breakers shall not be used in this anti-islanding fail-safe scheme; use the specified healthy-supply-held contactor or undervoltage release, subject to 5.9.3 approved alternatives.',
   '5.10.1 / 5.10.3':'Verify normal supply on all connected phases for at least 60 seconds before enabling connection/reconnection.',
   'Annex A':'Mandatory UV/OV, UF/OF, NVD for HV and at least one of the listed backup anti-islanding alternatives; ROCOF and vector shift form one alternative, not separate universal requirements.',
   'Annex C C1-C3':'Design pack includes CT/VT/CB location, ratio/class, relay inputs/elements/outputs, trip sequence, full relay settings, operating modes, existing EG and drawing revision/responsible designer details.',
   'Annex D D1':'NVD VT ratio uses primary/110 V LL, protection construction, accuracy <=5%, factor 1.9 for isolated-neutral systems and suitable burden.',
   '6.2 / 6.4 / 6.5':'Qualified signed secondary injection tests; additional approved plan, witness and primary anti-islanding tests for applicable complex schemes.',
  },
 },
 'NS238-Am0-20150504':{
  'title':'Ausgrid NS238 Supply Quality','edition':'Amendment 0, approved 2015-05-04',
  'sha256':'5179e84d899b3399b22942df37f9ab9c9e20b667b240cd225baf3d45f416e8ca',
  'currency':'User-supplied historical edition; latest online edition not independently verified',
  'clauses':{
   '6.2.2':'LV network compatibility Pst=1, Plt=0.8; these are not blanket customer emission allocations.',
   '6.2.3 Table 2':'LV voltage compatibility THD=8% with individual harmonic compatibility values; not a general current-THD limit or automatic customer allocation.',
   '6.2.4':'Use site-specific Power Quality Allocation where applicable; otherwise applicable equipment standards and the allocation process govern customer emissions.',
  },
 },
}


def source_linked(p,profile,evidence_id):
    return any(e.id==evidence_id and e.kind=='standard' and e.sha256==CATALOG[profile]['sha256'] and e.status=='accepted' for e in p.delivery.evidence)


def issues(p):
    from .readiness import accepted
    if p.delivery is None:return []
    d=p.delivery.design;policy=d.policy;out=[]
    ns194=policy.source_document_id=='NS194-Rev5-20260910'
    if str(p.get('site.dnsp','')).casefold()=='ausgrid' and not ns194:
        out.append('[Ausgrid sources] Select and review the supported NS194 source edition, or implement and verify a newer source profile before final release')
    ns238=policy.pq_source_document_id=='NS238-Am0-20150504'
    if ns194:
        for key in ('responsible_designer','designer_contact','drawing_revision','operating_modes','existing_generation_description','relay_manufacturer','relay_order_code','relay_full_settings_reference'):
            if not getattr(d,key):out.append(f'[NS194 Annex C] {key} is required')
        if not source_linked(p,policy.source_document_id,policy.evidence_id):out.append('[NS194 source] Review the exact uploaded Rev 5 PDF (SHA-256 must match the cited edition)')
        capacity=p.get('calc.inverter_ac_kva')
        if capacity is None:out.append('[NS194 4.1] Aggregate inverter capacity unknown')
        if policy.backstop_status=='unresolved' or not policy.backstop_basis:out.append('[NS194 1.3 / Table 2] Backstop applicability and dated source basis unresolved')
        if policy.backstop_status=='exempt' and not accepted(p,'backstop_exemption',policy.backstop_exemption_evidence_id):out.append('[NS194 1.3] Attach actual approved backstop exemption')
        if capacity is not None:
            mode=policy.communication_mode
            if policy.backstop_status=='enabled' and capacity<=200 and mode!='CSIP-Aus':out.append('[NS194 Table 2] Backstop-enabled <=200 kVA requires CSIP-AUS, not an inferred SCADA threshold')
            if policy.backstop_status=='enabled' and 200<capacity<=1000 and mode not in ('CSIP-Aus','SCADA'):out.append('[NS194 Table 2] Backstop-enabled >200 kVA to 1 MVA requires CSIP-AUS or SCADA as specified in the offer')
            if capacity>1000 and (policy.backstop_status=='enabled' or any(e.kind=='bess' for e in d.equipment)) and mode!='SCADA':out.append('[NS194 Table 2] >1 MVA backstop-enabled IES / BESS requires SCADA')
        if any(e.as4777_compliant is False for e in d.equipment) and not accepted(p,'annex_h_assessment'):out.append('[NS194 Annex H] Non-AS4777 scheme requires its agreed data/model/study submission, including applicable RMS/EMT requirements')
        if policy.site_type=='unresolved':out.append('[NS194 4.2] Classify commercial vs residential-cluster applicability')
        exemption=policy.site_type=='residential_cluster' and accepted(p,'interface_exemption',policy.interface_exemption_evidence_id)
        if capacity is not None and capacity>200 and not exemption:
            alternative=accepted(p,'alternative_failsafe',policy.alternative_failsafe_evidence_id)
            for b in d.breakers:
                if b.role=='eg_common' and b.trip_coil=='shunt' and not alternative:out.append(f'[NS194 5.9.2] {b.id}: shunt trip is prohibited for this fail-safe scheme; 5.9.3 alternatives need approved ISMP/Connection Agreement evidence')
                if b.role=='eg_common' and b.fail_position!='open':out.append(f'[NS194 5.9.1] {b.id}: healthy-supply failure must leave generation disconnected')
            c=d.control
            if not c.main_protection_supply or not c.backup_protection_supply or c.main_protection_supply==c.backup_protection_supply or not c.independent_supply_source:out.append('[NS194 5.2.1] Specify independent main/backup protection supplies and their source')
            if c.reconnection_healthy_s is None or c.reconnection_healthy_s<60:out.append('[NS194 5.10.1] All connected phases need >=60 s healthy supply before reconnection')
            if c.trip_signal_over_comms is None or c.grid_intertrip is None:out.append('[NS194 5.7/5.8] Assess inter-trip / remote trip communications applicability')
            if c.trip_signal_over_comms or c.grid_intertrip:
                if c.response_s is None or c.response_s>5:out.append('[NS194 5.7.4 / 5.8.2] Applicable trip-communications loss must disconnect within 5 s')
            for device in d.equipment:
                if device.as4777_compliant is None or not device.adjusted_settings_reference:out.append(f'[NS194 Annex C] {device.id}: record AS/NZS 4777.2 applicability/compliance and adjusted settings source')
            for f in d.protection:
                if f.applicability!='required':continue
                if not f.output_test_link or not f.local_indication:out.append(f'[NS194 5.12] {f.id}: output isolation/test link and local operation indication required')
                if not alternative and f.output_mode!='healthy_closed_trip_open':out.append(f'[NS194 5.9] {f.id}: verify healthy-held, fail-open trip circuit logic')
                if f.ansi=='watchdog' and any(other.id!=f.id and other.applicability=='required' and other.output_contact==f.output_contact for other in d.protection):out.append('[NS194 5.12.1] A separate relay-fail contact must be available for testing')
            functions={f.ansi for f in d.protection if f.applicability=='required'}
            for ansi in ('27','59','81U','81O'):
                if ansi not in functions:out.append(f'[NS194 Annex A] Required protection function missing: {ansi}')
            if not ('32R' in functions or '32F' in functions or 'intertrip' in functions or {'81R','78'}<=functions):out.append('[NS194 Annex A] Select a sourced backup anti-islanding alternative: GRP, GLFP, inter-trip, or ROCOF AND vector shift')
            if (p.get('connection.supply_voltage_v') or 0)>=1000:
                if '59N' not in functions:out.append('[NS194 5.6 / Annex A] HV >200 kVA requires NVD assessment and negotiated settings')
                for i in d.instruments:
                    if i.purpose!='NVD':continue
                    if i.kind!='VT' or i.ratio_secondary!=110 or i.ratio_primary!=p.get('connection.supply_voltage_v') or i.ratio_basis!='line_to_line':out.append(f'[NS194 Annex D D1] {i.id}: verify primary / 110 V line-to-line NVD VT ratio')
                    match=re.fullmatch(r'(\d+(?:\.\d+)?)P',i.accuracy_class)
                    if not match or float(match.group(1))>5:out.append(f'[NS194 Annex D D1] {i.id}: protection VT accuracy must be <=5% (e.g. 3P)')
                    if policy.isolated_neutral is None:out.append('[NS194 Annex D] Establish neutral earthing arrangement')
                    elif policy.isolated_neutral and (i.voltage_factor is None or i.voltage_factor<1.9):out.append(f'[NS194 Annex D] {i.id}: isolated-neutral voltage factor >=1.9 required')
                    if not i.construction or not i.burden_va:out.append(f'[NS194 Annex D] {i.id}: protection construction and burden required')
    if ns238:
        if not source_linked(p,policy.pq_source_document_id,policy.pq_evidence_id):out.append('[NS238 source] Review the exact supplied Amendment 0 PDF and confirm current project applicability')
        for a in d.assessments:
            if a.kind in ('voltage_thd_pct','current_thd_pct','flicker_pst','flicker_plt','voltage_change_pct'):
                if a.limit_type in ('compatibility_screening','unresolved'):out.append(f'[NS238 6.2.4] {a.id}: compatibility screening is not a customer emission allocation')
                if a.limit_type=='allocation' and not accepted(p,'pq_allocation',a.allocation_evidence_id):out.append(f'[NS238 6.2.4] {a.id}: attach reviewed site-specific Power Quality Allocation')
    return out


def commissioning_issues(p):
    from .readiness import accepted
    d=p.delivery.design
    if d.policy.source_document_id!='NS194-Rev5-20260910':return []
    capacity=p.get('calc.inverter_ac_kva') or 0
    funcs={f.ansi for f in d.protection if f.applicability=='required'}
    complex_scheme=capacity>200 and (capacity>500 or (p.get('connection.supply_voltage_v') or 0)>=1000 or d.control.trip_signal_over_comms or bool(funcs&{'59N','32F','32R','intertrip'}))
    required=[]
    if complex_scheme:required+=['approved_test_plan','witness_test']
    if {'81R','78'}<=funcs:required+=['primary_antiislanding']
    return [f'[NS194 6.4 / 6.5] Accepted evidence required: {kind}' for kind in required if not accepted(p,kind)]
