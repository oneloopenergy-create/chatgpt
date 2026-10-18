from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False, validate_default=True)


class Breaker(Record):
    id: str = Field(min_length=1, pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')
    role: Literal['incomer', 'eg_common', 'branch', 'isolation'] = 'branch'
    location: str = ''
    rating_a: float | None = Field(default=None, gt=0)
    breaking_ka: float | None = Field(default=None, gt=0)
    poles: int = Field(default=3, ge=1, le=4)
    trip_coil: Literal['shunt', 'undervoltage', 'none', 'unknown'] = 'unknown'
    coil_voltage_v: float | None = Field(default=None, gt=0)
    coil_supply: str = ''
    coil_terminal: str = ''
    feedback_terminal: str = ''
    fail_position: Literal['open', 'closed', 'unknown'] = 'unknown'


class Transformer(Record):
    id: str = Field(min_length=1, pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')
    rating_kva: float | None = Field(default=None, gt=0)
    primary_v: float | None = Field(default=None, gt=0)
    secondary_v: float | None = Field(default=None, gt=0)
    impedance_pct: float | None = Field(default=None, gt=0, lt=100)
    vector_group: str = ''
    resistance_pct: float | None = Field(default=None, ge=0)
    primary_node: str = ''
    secondary_node: str = ''
    dss_leadlag: Literal['lead', 'lag', 'unresolved'] = 'unresolved'
    location: str = ''
    source_ref: str = ''


class Cable(Record):
    id: str = Field(min_length=1, pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')
    from_id: str = ''
    to_id: str = ''
    cores: str = ''
    material: Literal['Cu', 'Al', 'unknown'] = 'unknown'
    size_mm2: float | None = Field(default=None, gt=0)
    length_m: float | None = Field(default=None, gt=0)
    installation: str = ''
    current_capacity_a: float | None = Field(default=None, gt=0)
    r_ohm_per_km: float | None = Field(default=None, ge=0)
    x_ohm_per_km: float | None = Field(default=None, ge=0)
    source_ref: str = ''


class SecondaryCircuit(Record):
    id: str = Field(min_length=1, pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')
    phase: Literal['L1', 'L2', 'L3', 'NVD'] = 'L1'
    secondary_s1: str = ''
    secondary_s2: str = ''
    test_input: str = ''
    test_return: str = ''
    relay_input: str = ''
    relay_return: str = ''
    earth_terminal: str = ''


class InstrumentTransformer(Record):
    id: str = Field(min_length=1, pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')
    kind: Literal['CT', 'VT'] = 'CT'
    purpose: Literal['protection', 'metering', 'NVD'] = 'protection'
    circuits: list[SecondaryCircuit] = Field(default_factory=list)
    location_id: str = ''
    phases: str = 'L1,L2,L3'
    ratio_basis: Literal['current', 'line_to_line', 'line_to_neutral', 'unresolved'] = 'unresolved'
    voltage_factor: float | None = Field(default=None, gt=0)
    construction: str = ''
    ratio_primary: float | None = Field(default=None, gt=0)
    ratio_secondary: float | None = Field(default=None, gt=0)
    accuracy_class: str = ''
    burden_va: float | None = Field(default=None, gt=0)
    winding: str = ''
    secondary_terminals: str = ''
    relay_input: str = ''
    earthing: str = ''
    test_block: str = ''
    source_ref: str = ''


class Equipment(Record):
    id: str = Field(min_length=1, pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')
    kind: Literal['pv', 'bess'] = 'pv'
    manufacturer: str = ''
    model: str = ''
    qty: int = Field(default=1, gt=0, strict=True)
    rated_kva: float | None = Field(default=None, gt=0)
    rated_kw: float | None = Field(default=None, gt=0)
    energy_kwh: float | None = Field(default=None, gt=0)
    dc_kwp: float | None = Field(default=None, gt=0)
    cec_reference: str = ''
    cec_evidence_id: str = ''
    as4777_compliant: bool | None = None
    adjusted_settings_reference: str = ''
    cec_expiry: date | None = None
    branch_cb: str = ''
    connection_node: str = 'EG_BUS'


class ProtectionFunction(Record):
    id: str = Field(min_length=1, pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')
    ansi: str = ''
    name: str = ''
    applicability: Literal['required', 'not_applicable', 'unresolved'] = 'unresolved'
    applicability_basis: str = ''
    relay_model: str = ''
    relay_input: str = ''
    output_contact: str = ''
    output_mode: Literal['healthy_closed_trip_open', 'trip_close_pulse', 'unresolved'] = 'unresolved'
    output_test_link: str = ''
    local_indication: str = ''
    terminal: str = ''
    setting: float | None = None
    setting_unit: str = ''
    delay_s: float | None = Field(default=None, ge=0)
    target_breakers: list[str] = Field(default_factory=list)
    fail_safe: str = ''
    setting_source: str = ''
    approved_evidence_id: str = ''


class SiteItem(Record):
    id: str = Field(min_length=1, pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')
    kind: Literal['connection', 'boundary', 'switchboard', 'transformer', 'pv', 'battery', 'room', 'access'] = 'switchboard'
    label: str = ''
    x_m: float = 0
    y_m: float = 0
    width_m: float = Field(default=1, gt=0)
    height_m: float = Field(default=1, gt=0)
    equipment_ids: list[str] = Field(default_factory=list)


class SiteRoute(Record):
    id: str = Field(min_length=1, pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')
    cable_id: str = ''
    item_ids: list[str] = Field(default_factory=list)


class Control(Record):
    controller: str = ''
    measurement_ct: str = ''
    soft_limit_kw: float | None = Field(default=None, ge=0)
    hard_limit_kw: float | None = Field(default=None, ge=0)
    response_s: float | None = Field(default=None, gt=0)
    response_source: str = ''
    communication_protocol: str = ''
    loss_of_comms_action: str = ''
    loss_of_power_action: str = ''
    watchdog_action: str = ''
    trip_breaker_ids: list[str] = Field(default_factory=list)
    independent_trip_path: str = ''
    recovery_interlock: str = ''
    reconnection_healthy_s: float | None = Field(default=None, ge=0)
    trip_signal_over_comms: bool | None = None
    grid_intertrip: bool | None = None
    main_protection_supply: str = ''
    backup_protection_supply: str = ''
    independent_supply_source: str = ''
    oem_client: str = ''
    capability_test_reference: str = ''
    rtu_model: str = ''
    heartbeat_timeout_s: float | None = Field(default=None, gt=0)
    gdl_reference: str = ''


class MSB(Record):
    manufacturer: str = ''
    assembly_id: str = ''
    modified: bool | None = None
    rating_a: float | None = Field(default=None, gt=0)
    short_time_ka: float | None = Field(default=None, gt=0)
    duration_s: float | None = Field(default=None, gt=0)
    prospective_fault_ka: float | None = Field(default=None, gt=0)
    temperature_rise_reference: str = ''
    discrimination_reference: str = ''
    standard_edition: str = ''


class HarmonicComponent(Record):
    order: int = Field(ge=2, le=50)
    rms: float = Field(ge=0)


class HarmonicStudy(Record):
    id: str = Field(min_length=1, pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')
    quantity: Literal['voltage', 'current'] = 'voltage'
    location: str = ''
    phase: Literal['L1', 'L2', 'L3'] = 'L1'
    fundamental_rms: float | None = Field(default=None, gt=0)
    source_reference: str = ''
    harmonics: list[HarmonicComponent] = Field(default_factory=list, max_length=49)

    @model_validator(mode='after')
    def unique_orders(self):
        orders=[h.order for h in self.harmonics]
        if len(set(orders))!=len(orders):raise ValueError('Duplicate harmonic orders are not permitted')
        return self


class Assessment(Record):
    id: str = Field(min_length=1, pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')
    kind: Literal['voltage_thd_pct', 'current_thd_pct', 'flicker_pst', 'flicker_plt', 'voltage_change_pct', 'fault_ka', 'discrimination'] = 'voltage_thd_pct'
    location: str = ''
    calculation_id: str = ''
    limit_type: Literal['allocation', 'equipment_standard', 'compatibility_screening', 'unresolved'] = 'unresolved'
    allocation_evidence_id: str = ''
    result: float | None = Field(default=None, ge=0)
    upper_limit: float | None = Field(default=None, ge=0)
    method: str = ''
    limit_source: str = ''
    evidence_id: str = ''
    reviewer: str = ''


class TestResult(Record):
    id: str = Field(min_length=1, pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')
    kind: Literal['secondary_injection', 'communications', 'backstop', 'interlock', 'inspection'] = 'secondary_injection'
    function_id: str = ''
    target_breaker: str = ''
    instrument: str = ''
    calibration_reference: str = ''
    injection_value: float | None = None
    measured_pickup: float | None = None
    unit: str = ''
    measured_time_s: float | None = Field(default=None, ge=0)
    maximum_time_s: float | None = Field(default=None, ge=0)
    tolerance_s: float | None = Field(default=None, ge=0)
    acceptance_source: str = ''
    scenario: str = ''
    trip_observed: bool | None = None
    outcome: Literal['not_tested', 'pass', 'fail'] = 'not_tested'
    operator: str = ''
    qualification: str = ''
    performed_on: date | None = None
    evidence_id: str = ''


class Policy(Record):
    source_document_id: str = ''
    pq_source_document_id: str = ''
    pq_evidence_id: str = ''
    site_type: Literal['commercial', 'residential_cluster', 'unresolved'] = 'unresolved'
    backstop_status: Literal['enabled', 'non_backstop', 'exempt', 'unresolved'] = 'unresolved'
    backstop_basis: str = ''
    backstop_exemption_evidence_id: str = ''
    interface_exemption_evidence_id: str = ''
    alternative_failsafe_evidence_id: str = ''
    isolated_neutral: bool | None = None
    title: str = ''
    dnsp: str = ''
    document_reference: str = ''
    edition: str = ''
    clause: str = ''
    applicability: str = ''
    source_url: str = ''
    evidence_id: str = ''
    reviewed_by: str = ''
    reviewed_on: date | None = None
    valid_until: date | None = None
    status: Literal['unverified', 'reviewed'] = 'unverified'
    required_protection_functions: list[str] = Field(default_factory=lambda: ['27', '59', '81U', '81O', '81R', '78', '32R', 'watchdog', 'loss_of_mains'])
    msb_declaration: Literal['required', 'not_applicable', 'unresolved'] = 'unresolved'
    msb_basis: str = ''
    communication_mode: Literal['CSIP-Aus', 'SCADA', 'other', 'unresolved'] = 'unresolved'
    communication_basis: str = ''


class Milestones(Record):
    submission_reference: str = ''
    submitted_on: date | None = None
    submitted_by: str = ''
    offer_reference: str = ''
    accepted_on: date | None = None
    payment_reference: str = ''
    job_number: str = ''
    der_register_number: str = ''
    inspection_booking: str = ''
    inspection_on: date | None = None
    permission_reference: str = ''
    energised_on: date | None = None


class Dispatch(Record):
    equipment_id: str
    active_kw: float
    reactive_kvar: float = 0


class OperatingPoint(Record):
    source_pu: float | None = Field(default=None, gt=0, le=1.2)
    load_bus: str = ''
    load_kw: float | None = Field(default=None, ge=0)
    load_kvar: float | None = None
    dispatch: list[Dispatch] = Field(default_factory=list)
    study_reference: str = ''


class Switchboard(Record):
    id: str = Field(min_length=1, pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')
    label: str = ''
    phases: str = ''
    installation_status: Literal['existing', 'new', 'unresolved'] = 'unresolved'
    location: str = ''


class Design(Record):
    responsible_designer: str = ''
    designer_contact: str = ''
    drawing_revision: str = ''
    drawing_number: str = ''
    drawing_date: date | None = None
    drawing_checker: str = ''
    design_company: str = ''
    switchboards: list[Switchboard] = Field(default_factory=list)
    operating_modes: str = ''
    existing_generation_description: str = ''
    connection_point: str = ''
    ownership_boundary: str = ''
    ownership_boundary_cable_id: str = ''
    msb_id: str = 'MSB'
    eg_bus_id: str = 'EG_BUS'
    relay_id: str = 'RELAY1'
    relay_model: str = ''
    relay_manufacturer: str = ''
    relay_order_code: str = ''
    relay_full_settings_reference: str = ''
    site_survey_reference: str = ''
    site_coordinates_verified_by: str = ''
    site_north_deg: float = Field(default=0, ge=0, lt=360)
    source_fault_mva: float | None = Field(default=None, gt=0)
    source_x_r: float | None = Field(default=None, gt=0)
    upstream_fault_limit_ka: float | None = Field(default=None, gt=0)
    operating_point: OperatingPoint = Field(default_factory=OperatingPoint)
    breakers: list[Breaker] = Field(default_factory=list)
    transformers: list[Transformer] = Field(default_factory=list)
    cables: list[Cable] = Field(default_factory=list)
    instruments: list[InstrumentTransformer] = Field(default_factory=list)
    equipment: list[Equipment] = Field(default_factory=list)
    protection: list[ProtectionFunction] = Field(default_factory=list)
    site_items: list[SiteItem] = Field(default_factory=list)
    site_routes: list[SiteRoute] = Field(default_factory=list)
    control: Control = Field(default_factory=Control)
    msb: MSB = Field(default_factory=MSB)
    harmonic_studies: list[HarmonicStudy] = Field(default_factory=list)
    assessments: list[Assessment] = Field(default_factory=list)
    tests: list[TestResult] = Field(default_factory=list)
    policy: Policy = Field(default_factory=Policy)
    milestones: Milestones = Field(default_factory=Milestones)

    @model_validator(mode='after')
    def unique_ids(self):
        ids = [obj.id for name in ('switchboards','breakers','transformers','cables','instruments','equipment','protection','site_items','site_routes','harmonic_studies','assessments','tests') for obj in getattr(self, name)]
        ids += [c.id for i in self.instruments for c in i.circuits]
        reserved={'GRID','POC',self.msb_id,self.eg_bus_id,self.relay_id}
        if len(reserved)!=5 or set(ids)&reserved:
            raise ValueError('GRID, POC, MSB, EG bus and relay node IDs must be distinct and must not be reused as record IDs')
        if len(ids) != len(set(ids)):
            raise ValueError('Every record must have a unique ID across the engineering design')
        return self

    def fingerprint(self):
        data = self.model_dump(mode='json', exclude={'milestones', 'tests'})
        # Referencing an uploaded file must not invalidate that same file. Physical
        # design/settings remain in the hash; file IDs and review metadata do not.
        def strip_refs(value):
            if isinstance(value, dict):
                return {k:strip_refs(v) for k,v in value.items() if not k.endswith('evidence_id') and k not in ('reviewed_by','reviewed_on','reviewer')}
            if isinstance(value, list):return [strip_refs(v) for v in value]
            return value
        data=strip_refs(data)
        return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


EVIDENCE_KINDS = Literal['standard', 'cec_certificate', 'site_survey', 'msb_declaration', 'temperature_rise', 'discrimination', 'pq_study', 'pq_allocation', 'fault_study', 'submission_receipt', 'connection_offer', 'approved_drawings', 'approved_settings', 'payment', 'der_registration', 'capability_test', 'scada_test', 'communications_test', 'secondary_injection', 'ccew', 'inspection', 'permission_to_connect', 'approved_test_plan', 'witness_test', 'primary_antiislanding', 'alternative_failsafe', 'interface_exemption', 'backstop_exemption', 'annex_h_assessment', 'other']


class Evidence(Record):
    id: str
    kind: EVIDENCE_KINDS
    filename: str
    sha256: str
    size: int
    uploaded_at: str
    uploaded_by: str
    issuer: str = ''
    reference: str = ''
    issued_on: date | None = None
    design_hash: str = ''
    status: Literal['uploaded', 'accepted', 'rejected'] = 'uploaded'
    reviewed_by: str = ''
    reviewed_at: str | None = None
    review_note: str = ''


class Transition(Record):
    stage: str
    completed_at: str
    completed_by: str
    design_hash: str
    notes: str = ''


class Release(Record):
    id: str
    scope: str
    created_at: str
    created_by: str
    design_hash: str
    sha256: str
    files: list[str]


class SimulationRun(Record):
    id: str
    created_at: str
    design_hash: str
    engine_version: str
    frequency_hz: float
    converged: bool
    source_kw: float
    source_kvar: float
    losses_kw: float
    voltages: dict[str, list[float]]
    currents: dict[str, list[float]]
    loading_pct: dict[str, float]
    limitations: list[str]


class Delivery(Record):
    simulation: SimulationRun | None = None
    design: Design = Field(default_factory=Design)
    evidence: list[Evidence] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)
    releases: list[Release] = Field(default_factory=list)
