# Engineering references supplied by the user

## Current implementation

Schemdraw supplies the isolator switch vector geometry in legacy template SLDs through
`gridease/sld/symbols.py`. Rendering uses its headless SVG backend and preserves
wire terminal positions. GridEasy continues to own diagram layout, equipment labels,
parameter-version tracking and engineer review gates. This does not claim IEC or
DNSP certification of the diagram. The project uses released Schemdraw 0.22;
the uploaded master archive identifies itself as development version 0.23.

OpenDSSDirect.py 0.9.4 is an optional `engineering` dependency. Run:

```sh
uv pip install --python .venv/bin/python -e '.[dev,engineering]'
.venv/bin/python scripts/engineering_reference_smoke.py
```

The smoke script creates an isolated context and verifies a synthetic 400 V,
three-phase, 50 Hz, 100 kW / 20 kvar load. It checks convergence, actual power and
phase voltages. Engine defaults must not substitute for verified project data.
The engineering delivery workspace also exposes a typed, project-specific steady-state
simulation endpoint; see `engineering-delivery.md`. No automatic study approval is enabled.

## Next integration boundary

A customer study needs an explicit network model: buses and phase connections,
line lengths and impedances, source impedance/short-circuit strength, transformer
winding ratings/vector groups/impedances, load P/Q and time profile, inverter control
modes and operating points. Inverter nameplate kVA alone is not dispatched kW.

Use one DSS context per study. Build DSS commands only from validated typed fields;
do not interpolate customer free text into engine commands or execute uploaded DSS
scripts. Store model input versions, solver version, frequency, convergence status
and limitations with each result. Changing a study input must invalidate its report.
Voltage rise, losses and loading can then be checked against engineer-approved
limits. Fault and protection studies need separate validated models and controls.

## Licenses and provenance

The uploaded repositories are reference material, not product requirements.
No master-archive installation scripts or documentation instructions were executed.
Released packages were installed through the package registry with normal verification.

- Schemdraw: MIT; retain its copyright and permission notice when redistributing
  covered code. The supplied archive notice is preserved in
  `third-party/Schemdraw-LICENSE.txt`; the installed package carries its own notice.
- OpenDSSDirect.py: the supplied license is a custom license with five conditions,
  including notice retention, research-entity source-publication requirements and
  naming restrictions for modified versions. It should not be described as MIT or
  plain BSD. The complete supplied notice is in
  `third-party/OpenDSSDirect.py-LICENSE.txt`.
- The OpenDSS engine/backend is a separate dependency; its bundled licenses also
  need to accompany redistributions as applicable. This change does not vendor or
  rename either project.

## Uploaded AU / NZ drawing corpus

See [reference review and implemented improvements](sld-reference-optimisation.md).
The typed engineering SLD uses its own terminal-aware vector primitives; the legacy
Schemdraw templates remain available. Original case PDFs are not bundled.
