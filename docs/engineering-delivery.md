# Engineering delivery workspace

The **工程交付 · 7 阶段** tab covers preparation, review, manual portal submission,
offer records, construction/commissioning and final handover. New projects enable it;
existing projects retain their data and can activate it explicitly.

## Start a real project

1. Enter the client, site, DNSP, connection voltage and capacity in Design inputs.
2. Open Engineering delivery, record the responsible employee and enter the typed
   engineering schedule. The blank PV skeleton supplies identifiers/connectivity
   only; it does not supply ratings, settings or approved engineering assumptions.
3. Enter real breaker/contactor coils and supplies, transformer ratios/impedance/vector
   groups, cable endpoints/specifications, generation equipment and current CEC
   evidence, CT/VT phase secondary terminal mappings, relay I/O, function applicability
   and proposed settings. Equipment in this schedule becomes authoritative for
   legacy capacity calculations; the old parameter editor cannot contradict it.
4. Enter surveyed geometry and route IDs. The site drawing uses those coordinates;
   it does not invent a cadastral or aerial plan.
5. Select the supplied standard edition, upload its original PDF as `standard`, and
   record the engineer's source/edition/clause/applicability review. The catalog
   verifies the supplied PDF hash; it does not certify currency against the live
   DNSP website. Fill CEC evidence IDs separately for each equipment model.
6. Enter controller/soft/hard limits, actual response requirements, loss-of-power,
   communications/watchdog behaviour and restoration interlocks. Mark protection
   functions not applicable only with a documented engineering basis.
7. Preview and review generated documents, resolve missing information, and record
   engineer sign-off under Documents. Record actual external signatures as evidence.
8. Complete the first three stages and freeze a **design** release. Upload it manually
   in the appropriate current DNSP portal along with any required official forms.
   The generated application schedule is not a replacement official form.

Every upload requires an issuer, reference and operator. Uploading does not mean
acceptance. A reviewer must record the basis/scope after inspecting the actual file.
These names are audit records, not authenticated identities or cryptographic signatures.
Attachments download as files, never execute or render as application code.

## Generated deliverables

| Deliverable | Output | Source |
|---|---|---|
| Electrical SLD | SVG | Declared electrical connectivity, breakers, equipment, cables, CT/VT and transformer data |
| Three-phase protection schematic | SVG | Phase-by-phase secondary S1/S2, test, relay input/return, earth, physical output and trip coil terminal records |
| Tripping matrix | CSV | Function applicability, setpoints, relay I/O, target CBs, fail-safe logic and setting sources |
| Site layout | SVG | Survey-referenced equipment coordinates, ownership/POC and cable route points |
| Control/fail-safe statement | Printable HTML | Project-specific controller, thresholds, response, independence and restoration data |
| MSB declaration preparation | Printable HTML | Assembly/manufacturer/withstand/temperature/discrimination inputs; actual manufacturer execution is separate |
| Technical study review | Printable HTML | External reviewed reports, sourced limits, scalar comparisons and optional spectral THD calculation |
| Submission/application schedule | Printable HTML | Client/site/capacity, applicable source profile, deliverable index and manual portal action |
| Commissioning plan | Printable HTML | Required protection functions and targets, settings, communications and physical test tasks |
| Secondary injection record | Printable HTML | Entered measurements, time tolerance, operator, calibration and original signed evidence |
| Communications/backstop record | Printable HTML | Entered capability, failure scenario and interlock results plus evidence |
| Offer/final handover register | Printable HTML | Actual submission, offer, payment, job/DER IDs, inspection/CCEW/permission files |

Use **打印 / 保存 PDF** in previews when a portal requires PDF. Draft drawings and
preparation templates are not construction-certified drawings, actual tests or certificates.

## Seven stages and release scopes

- SLD: physical connectivity, equipment and primary/secondary data must be complete.
- Design pack: protection, controls, diagrams and identified applicable source checks.
- Pre-submission: reviewed source PDF, model-specific CEC, survey, MSB evidence where
  applicable, studies/limits and current engineer-reviewed design documents.
- Submission: an employee records actual portal receipt/date and resolves RFIs.
- Offer: actual accepted offer/payment/job/DER references and approved drawings/settings.
- Commissioning: linked approved settings, calibrated qualified secondary tests,
  capability/SCADA evidence and witnessed failure/restoration scenarios. Applicable
  NS194 complex schemes require approved test-plan/witness records; ROCOF/vector-shift
  schemes require the relevant primary anti-islanding record.
- Energisation: CCEW, inspection and actual permission evidence plus actual dates.

`design`, `commissioning`, and `handover` releases have separate gates. The design
release does not wait for construction tests. Original attachments, the typed design
JSON, document hashes/input versions and a manifest are frozen into a SHA-256 checked
ZIP. Later changes never overwrite a prior release. Old API final export cannot bypass
these gates. Technical evidence is bound to its design; changing design inputs requires
current evidence/review. Later milestone fields do not invalidate unchanged design drawings.
A failed or modified test invalidates downstream completion.

## Supplied Ausgrid references

- NS194 Revision 5, approved **10 September 2026**, supplied SHA-256
  `3315658d09b929a7c0cacb7ce9e646bf42d47e87df9bfafd57c2bc317dd6a071`.
  Implemented clause checks include >200 kVA interface scope, applicable residential
  exceptions, Annex A alternatives, fail-safe shunt-trip prohibition (§5.9.2) and
  approved §5.9.3 alternatives, independent supplies, 5 s applicable trip-link failure,
  >=60 s all-phase healthy reconnection, CT/VT/NVD records, separate watchdog test
  contact, output test links/local indication, Annex C revision/designer details,
  source-qualified Table 2 communications, and Annex B timing/pickup tolerances.
- NS238 Amendment 0, approved **4 May 2015**, supplied SHA-256
  `5179e84d899b3399b22942df37f9ab9c9e20b667b240cd225baf3d45f416e8ca`.
  Compatibility values (voltage THD 8%, Pst 1, Plt 0.8) are never automatically used
  as a customer allocation. The applicable allocation/equipment-standard basis and
  external assessment remain required.

These are identified uploaded editions. Neither “current official edition” nor
independent approval of every possible project arrangement is claimed. MSB >100 A,
specific SCADA size bands and negotiated settings must not be inferred from the user's
initial summary when the actual source/applicability differs. Other DNSP sources and
licensed standards still require their current approved project review.

## Calculations and boundaries

The optional OpenDSS engine solves the explicit balanced 50 Hz snapshot model with
entered source strength, cable R/X/length/ampacity, transformer impedance/resistance/
winding phase relationship, load P/Q and asset dispatch. Both LV and explicitly modelled
Dyn1/Dyn11 HV/LV cases are exercised. It reports actual bus voltages, line currents,
loading and model losses. It refuses missing/disconnected inputs and over-nameplate
dispatch. It is not a harmonic, flicker, earth-fault, EMT or protection coordination study.
Do not infer grid approval from convergence. Use genuine external specialist study reports
for those aspects. For entered harmonic spectra, voltage/current THD is calculated as
`100 * sqrt(sum(harmonic_rms**2)) / fundamental_rms`; no missing spectrum is assumed zero.

The application still has no employee login/role control or managed backup service.
Run locally on loopback or behind company-managed authenticated access. Back up the
entire `GRIDEASE_DATA` directory (default `data/`), including `projects/`, `attachments/`
and `releases/`, with the server stopped for a consistent backup. Do not publicly expose
this local application or treat typed employee names as authenticated signatories.

## Verification

Run `python -m pytest -q`; install `.[dev,engineering]` to include native-engine tests.
Optional engine tests are explicitly skipped when that extra is absent. Regression tests
use synthetic fixtures, including their test-only standard identity, never assert an
actual customer installation is compliant. Browser validation covers typed form/import,
SVG preview, actual supplied PDF upload/review, solver result display, scoped ZIP download,
blocked incomplete final export and desktop/mobile layout.

Python 3.12 is validated here. The Windows startup script now disables PyYAML's optional
C extension and uses basic Uvicorn/h11 to reduce native builds when using Python 3.15.
Python 3.15 on the user's Windows machine has not been executed by this environment;
optional native OpenDSS/backend availability must be checked separately on that platform.
