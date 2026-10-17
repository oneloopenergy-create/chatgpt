"""Validate OpenDSS integration capability with a synthetic, explicit 50 Hz circuit.

This is a dependency/solver smoke test, NOT a study of a customer project.
Run: .venv/bin/python scripts/engineering_reference_smoke.py
Requires the optional engineering extra. Each run creates an isolated DSS context.
"""
from math import isclose

from opendssdirect import dss


def main():
    context = dss.NewContext()
    # This synthetic load is deliberately explicit; no customer data or assumptions
    # are imported into GridEasy and no report is marked engineer-approved.
    context("""
        set defaultbasefrequency=50
        New Circuit.reference basekv=0.4 pu=1.0 phases=3 bus1=sourcebus frequency=50
        New Load.reference bus1=sourcebus phases=3 conn=wye kv=0.4 kw=100 kvar=20
        set frequency=50
        solve
    """)
    if not context.Solution.Converged():
        raise RuntimeError("Synthetic reference circuit did not converge")
    power = context.Circuit.TotalPower()
    # DSS reports source consumption with negative signs. Confirm actual power,
    # not merely convergence: a frequency mismatch can converge with no load.
    if not isclose(context.Solution.Frequency(), 50):
        raise RuntimeError("Reference solver frequency is not 50 Hz")
    if not (isclose(-power[0], 100, abs_tol=0.01) and isclose(-power[1], 20, abs_tol=0.01)):
        raise RuntimeError(f"Unexpected reference power: {power}")
    voltage = context.Circuit.AllBusVMag()
    if len(voltage) != 3 or not all(225 < v < 235 for v in voltage):
        raise RuntimeError(f"Unexpected phase voltages: {voltage}")
    print("PASS: isolated OpenDSS context, 50 Hz, converged, 100 kW / 20 kvar, three phase voltages checked.")
    print("Synthetic dependency validation only; no customer project has been simulated.")


if __name__ == "__main__":
    main()
