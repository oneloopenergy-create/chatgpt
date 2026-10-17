"""Deterministic calculations on explicitly entered engineering measurements."""
import math


def harmonic_thd(study):
    if study.fundamental_rms is None or not study.harmonics or not study.source_reference:
        raise ValueError(f'{study.id}: fundamental RMS, harmonic spectrum and source required; an empty spectrum is not zero distortion')
    return 100*math.sqrt(sum(h.rms*h.rms for h in study.harmonics))/study.fundamental_rms


def assessment_value(p,assessment):
    if not assessment.calculation_id:return assessment.result
    study=next((s for s in p.delivery.design.harmonic_studies if s.id==assessment.calculation_id),None)
    if study is None:raise ValueError(f'{assessment.id}: linked harmonic spectrum not found')
    expected='voltage_thd_pct' if study.quantity=='voltage' else 'current_thd_pct'
    if assessment.kind!=expected:raise ValueError(f'{assessment.id}: quantity/type mismatch; voltage THD and current THD are separate')
    if assessment.location!=study.location:raise ValueError(f'{assessment.id}: study location mismatch')
    return harmonic_thd(study)
