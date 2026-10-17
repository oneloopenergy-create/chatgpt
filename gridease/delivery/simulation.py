"""Explicit balanced 50 Hz snapshot model. Never execute uploaded DSS commands."""
import math
import re
import uuid
from .model import SimulationRun
from .readiness import design_hash
from ..core.model import now


def solve(p):
    try:from opendssdirect import dss
    except ImportError:raise ValueError('Install the engineering extra: python -m pip install -e ".[engineering]"')
    d=p.delivery.design;op=d.operating_point
    missing=[]
    for val,name in [(p.get('connection.supply_voltage_v'),'supply voltage'),(d.source_fault_mva,'source fault MVA'),(d.source_x_r,'source X/R'),(op.source_pu,'source per-unit voltage'),(op.load_kw,'load kW'),(op.load_kvar,'load kvar'),(op.load_bus,'load bus'),(op.study_reference,'study source/reference')]:
        if val is None or val=='':missing.append(name)
    if not d.cables:missing.append('line impedance model')
    for c in d.cables:
        if any(v is None for v in (c.r_ohm_per_km,c.x_ohm_per_km,c.length_m,c.current_capacity_a)):missing.append(f'{c.id}: R/X/length/ampacity')
        if not c.from_id or not c.to_id:missing.append(f'{c.id}: endpoints')
    for t in d.transformers:
        if any(v is None for v in (t.rating_kva,t.primary_v,t.secondary_v,t.impedance_pct,t.resistance_pct)) or not t.primary_node or not t.secondary_node or t.dss_leadlag=='unresolved':missing.append(f'{t.id}: full transformer equivalent including R, primary/secondary nodes and sourced phase lead/lag')
        if t.vector_group not in ('Dyn1','Dyn11'):missing.append(f'{t.id}: this solver currently supports explicitly modelled Dyn1/Dyn11 windings only')
    if missing:raise ValueError('Study cannot run without: '+', '.join(missing))
    # Constrain every identifier used in the command language, including node names.
    names=[op.load_bus]+[v for c in d.cables for v in (c.id,c.from_id,c.to_id)]+[v for t in d.transformers for v in (t.id,t.primary_node,t.secondary_node)]+[e.id for e in d.equipment]
    if any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*',v) for v in names):raise ValueError('DSS model identifiers must contain letters, digits, underscores or hyphens only')
    buses={x for c in d.cables for x in (c.from_id,c.to_id)}|{x for t in d.transformers for x in (t.primary_node,t.secondary_node)}
    if 'GRID' not in buses or op.load_bus not in buses:raise ValueError('GRID and the load bus must exist in the cable model')
    # Assert electrical reachability before solving; convergence of isolated nodes
    # or a zero-load circuit must not be mistaken for a valid model.
    graph={}
    for a,b in [(c.from_id,c.to_id) for c in d.cables]+[(t.primary_node,t.secondary_node) for t in d.transformers]:
        graph.setdefault(a,set()).add(b);graph.setdefault(b,set()).add(a)
    seen={'GRID'};todo=['GRID']
    while todo:
        a=todo.pop()
        for b in graph.get(a,set())-seen:seen.add(b);todo.append(b)
    if not buses<=seen:raise ValueError('Model contains disconnected electrical buses')
    if set(x.equipment_id for x in op.dispatch)!={e.id for e in d.equipment}:raise ValueError('Provide an explicit operating point for every generation/battery asset')
    if len({x.equipment_id for x in op.dispatch})!=len(op.dispatch):raise ValueError('Duplicate dispatch asset')
    context=dss.NewContext()
    v=p.get('connection.supply_voltage_v');z=v*v/(d.source_fault_mva*1e6)
    r=z/math.sqrt(1+d.source_x_r*d.source_x_r);x=r*d.source_x_r
    context('set defaultbasefrequency=50')
    context(f'new circuit.study bus1=GRID phases=3 basekv={v/1000} pu={op.source_pu} frequency=50 r1={r} x1={x} r0={r} x0={x}')
    for c in d.cables:
        context(f'new line.{c.id} phases=3 bus1={c.from_id} bus2={c.to_id} length={c.length_m/1000} units=km r1={c.r_ohm_per_km} x1={c.x_ohm_per_km} r0={c.r_ohm_per_km} x0={c.x_ohm_per_km} c1=0 c0=0 normamps={c.current_capacity_a}')
    for t in d.transformers:
        if t.resistance_pct>t.impedance_pct:raise ValueError(f'{t.id}: R% exceeds total impedance%')
        xx=math.sqrt(t.impedance_pct**2-t.resistance_pct**2)
        context(f'new transformer.{t.id} phases=3 windings=2 buses=[{t.primary_node},{t.secondary_node}] conns=[delta,wye] kvs=[{t.primary_v/1000},{t.secondary_v/1000}] kvas=[{t.rating_kva},{t.rating_kva}] %rs=[{t.resistance_pct/2},{t.resistance_pct/2}] xhl={xx} %noloadloss=0 %imag=0 leadlag={t.dss_leadlag}')
    kv_by_bus={'GRID':v/1000}
    # Transformer voltage changes are propagated over lines without inventing a secondary voltage.
    for _ in range(len(buses)+1):
        for t in d.transformers:
            kv_by_bus[t.primary_node]=t.primary_v/1000;kv_by_bus[t.secondary_node]=t.secondary_v/1000
        for c in d.cables:
            if c.from_id in kv_by_bus and c.to_id not in kv_by_bus:kv_by_bus[c.to_id]=kv_by_bus[c.from_id]
            if c.to_id in kv_by_bus and c.from_id not in kv_by_bus:kv_by_bus[c.from_id]=kv_by_bus[c.to_id]
    if op.load_bus not in kv_by_bus:raise ValueError('Load nominal voltage unresolved')
    context(f'new load.site phases=3 bus1={op.load_bus} conn=wye kv={kv_by_bus[op.load_bus]} kw={op.load_kw} kvar={op.load_kvar} model=1')
    for dispatch in op.dispatch:
        e=next(e for e in d.equipment if e.id==dispatch.equipment_id)
        bus=e.connection_node
        if bus not in seen or bus not in kv_by_bus:raise ValueError(f'{e.id}: dispatch bus not connected')
        if e.rated_kva is None or math.hypot(dispatch.active_kw,dispatch.reactive_kvar)>e.rated_kva*e.qty+1e-6:raise ValueError(f'{e.id}: dispatch exceeds declared nameplate kVA')
        if e.kind=='pv' and dispatch.active_kw<0:raise ValueError('PV cannot be dispatched as a charging load')
        kind='generator' if dispatch.active_kw>=0 else 'load'
        kw=dispatch.active_kw if kind=='generator' else -dispatch.active_kw
        kvar=dispatch.reactive_kvar if kind=='generator' else -dispatch.reactive_kvar
        context(f'new {kind}.{e.id} phases=3 bus1={bus} conn=wye kv={kv_by_bus[bus]} kw={kw} kvar={kvar} model=1')
    context('set frequency=50')
    context.Solution.Solve()
    if not context.Solution.Converged():raise ValueError('OpenDSS did not converge; do not use this run as a passing study')
    voltages={}
    for name in context.Circuit.AllBusNames():
        context.Circuit.SetActiveBus(name);voltages[name]=context.Bus.VMagAngle()[::2]
    currents={};loading={}
    for c in d.cables:
        context.Circuit.SetActiveElement('Line.'+c.id);amps=context.CktElement.CurrentsMagAng()[::2][:3]
        currents[c.id]=amps;loading[c.id]=max(amps,default=0)/c.current_capacity_a*100
    power=context.Circuit.TotalPower()
    return SimulationRun(id=uuid.uuid4().hex[:16],created_at=now(),design_hash=design_hash(p),engine_version=context.Basic.Version(),frequency_hz=context.Solution.Frequency(),converged=True,source_kw=-power[0],source_kvar=-power[1],losses_kw=context.Circuit.Losses()[0]/1000,voltages=voltages,currents=currents,loading_pct=loading,limitations=['Balanced three-phase constant-PQ snapshot only; entered source and positive-sequence impedances.','Zero-sequence parameters duplicate positive sequence solely for this balanced solve; not suitable for earth-fault or protection studies.','No harmonic/flicker/EMT, transient protection, inverter fault-current or certified discrimination assessment.','Transformer core loss, line shunt capacitance and voltage-dependent controls excluded; explicitly simplified study.','Engineer must review the actual model, operating scenarios and DNSP acceptance limits.'])
