"""Validate editable engineering inputs before they reach calculation functions."""
import math
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from ..rules.library import dnsp_pack
from ..sld.generator import TOPOLOGIES


class Inverter(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)
    manufacturer: str = Field(min_length=1)
    model: str = Field(min_length=1)
    qty: int = Field(default=1, gt=0, strict=True)
    rated_ac_kva: float = Field(gt=0, allow_inf_nan=False)
    dc_kwp: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class Battery(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)
    manufacturer: str = Field(min_length=1)
    model: str = Field(min_length=1)
    qty: int = Field(default=1, gt=0, strict=True)
    pcs_kva: float = Field(gt=0, allow_inf_nan=False)
    energy_kwh: float | None = Field(default=None, gt=0, allow_inf_nan=False)


def validate_parameter(key, value):
    if key == "equipment.pv_inverters":
        return [v.model_dump(exclude_none=True) for v in TypeAdapter(list[Inverter]).validate_python(value)]
    if key == "equipment.bess":
        return [v.model_dump(exclude_none=True) for v in TypeAdapter(list[Battery]).validate_python(value)]
    if key.endswith(("_date", "_expiry")):
        if not isinstance(value, str):
            raise ValueError(f"{key} must be an ISO date (YYYY-MM-DD)")
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError()
        except ValueError:
            raise ValueError(f"{key} must be a valid ISO date (YYYY-MM-DD)")
    if key == "site.dnsp":
        return dnsp_pack(value)["dnsp"]
    if key == "design.topology" and value not in TOPOLOGIES:
        raise ValueError("Unsupported topology. Choose: " + ", ".join(sorted(TOPOLOGIES)))
    positive = {"connection.supply_voltage_v", "connection.transformer_kva", "inverter.fault_multiplier", "bess.life_years", "connection.scr", "bess.capex_per_kwh", "bess.c_rate", "pv.yield_kwh_per_kwp_day", "bess.round_trip_eff"}
    nonnegative = {"pv.dc_kwp", "connection.max_demand_kva", "export.requested_kw", "generation.max_kw",
                   "connection.max_import_kw", "site.existing_eg_kva", "bess.charge_kw", "bess.discharge_kw", "tariff.import_peak_c_per_kwh", "tariff.import_offpeak_c_per_kwh", "tariff.export_c_per_kwh"}
    if key in positive | nonnegative:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{key} must be a finite number")
        if value < 0 or (key in positive and value == 0):
            raise ValueError(f"{key} must be {'positive' if key in positive else 'zero or greater'}")
    if key == "bess.round_trip_eff" and value > 1:
        raise ValueError("Battery efficiency must be greater than zero and at most 1")
    if key == "load.profile_kw":
        if not isinstance(value, list) or len(value) != 24 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in value):
            raise ValueError("Load profile must contain 24 finite, nonnegative hourly kW values")
    if key == "tariff.peak_hours":
        if not isinstance(value, list) or any(type(v) is not int or not 0 <= v <= 23 for v in value):
            raise ValueError("Peak hours must be a list of whole hours from 0 to 23")
    if "'" in key or not key or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_." for c in key):
        raise ValueError("Parameter keys may only contain letters, numbers, underscores and dots")
    return value
