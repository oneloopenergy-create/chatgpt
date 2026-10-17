# GridEasy — AI engineering platform for Australian distribution network connections (phase 0 prototype)

GridEasy turns the project information for 100 kW – 5 MW commercial and industrial PV and battery projects into a
**draft** DNSP connection application package. A registered engineer then reviews and signs it.
GridEasy is a co-pilot for engineers. It does not replace DNSP/AEMO assessment or a registered engineer's sign-off.

## Quick start

**Windows:** install [Python 3.11+](https://www.python.org/downloads/) (tick "Add python.exe to PATH"), download or clone
this repository, then double-click `start.bat`. It creates a virtual environment, installs dependencies, and opens
http://localhost:8000.

**macOS / Linux:**

```bash
uv venv && uv pip install -e ".[dev]"
.venv/bin/uvicorn gridease.api.app:app --reload     # open http://localhost:8000
.venv/bin/python -m pytest -q
```

Project data is stored in `./data/projects/<id>.json` by default; set `GRIDEASE_DATA` to change the location.
Each project is stored separately and can be deleted in one step.

## Five-step workflow → code

| Step | Module | What it does |
|---|---|---|
| 1 Smart intake | `gridease/intake/extract.py` | Extracts fields from a free-text brief and keeps the source text as evidence. Every extracted value is an **unconfirmed assumption**. The extractor is rule-based for now; it is the baseline and fallback for a future LLM extractor hosted in Australia |
| 2 Rule matching | `gridease/rules/` | Versioned YAML rule packs: ENA, AS/NZS 4777.2, the CEC list, and Ausgrid / Endeavour / Essential / Energex / Ergon |
| 3 Design | `gridease/calc/engineering.py`, `gridease/sld/generator.py` | Deterministic calculations for capacity, connection path, rated and fault current, central protection and the export scheme. Generates a project-specific single line diagram (SVG) from the project topology |
| 4 Compliance and export limits | `gridease/compliance/checks.py` | Every finding expands to show the clause, the parameters involved, the issue and a suggested fix |
| 5 Sign-off and package | `gridease/package/` | Produces 8 documents and bundles them in DNSP order. The final package has gating rules (see below) |
| DNSP RFIs | `core/model.py` (`open_rfi`) | Records each RFI round and lists the documents it affects |
| Battery economics | `gridease/calc/bess.py` | Hourly typical-day simulation; calculates payback for each battery size and recommends one |

## Core guarantees (all covered by tests)

- **Single source of truth**: each parameter is stored once, with a source (`user_input / brief_extract / rule / calculation / assumption`) and a version. A calculated value's source names its inputs and their versions, e.g. `calc:capacity_summary(equipment.pv_inverters@v1,…)`.
- **A parameter change makes dependent documents stale**: each document records the parameter versions it used. When a parameter changes, every SLD, table or form that references it is marked `stale`.
- **Sign-off is bound to a content hash**: if a regenerated document's content changes, its previous sign-off no longer applies. A stale document cannot be signed off.
- **Final package gating**: a final package requires all of the following:
  - no error-level findings
  - verified rule packs (`verified: true`)
  - every assumption confirmed
  - no stale documents
  - the SLD and the protection settings signed off by a registered engineer

  A draft package can be downloaded at any time; its file names carry a `DRAFT_` prefix.
- AI only extracts and drafts; it **never produces numbers**. `calc.*` and `rules.*` cannot be edited through the API.

## Rule packs and their status

| Pack | Status | Contents |
|---|---|---|
| `dnsp_ausgrid.yaml` v0.3 | **Research seeds — not approved for engineering use** | 19 cited rules plus 4 GridEasy review flags. The Ausgrid rules (AG-R001–R013) apply interface protection above 200 kVA (NS194 §5.4.2) and the 30 kW export option for >30–200 kVA. AG-001/002 cite NS194 Rev5. The NSW Emergency Backstop rules (AUS-EB-001–004) depend on dates. NS194 protection *settings* are `TBC` |
| `dnsp_endeavour.yaml` v0.2 | Research seeds | EE-001–003 from PDI 5000 am6 Part A (LV protection scope 30–1500 kVA; consultation above 500 kVA; ESS included in aggregate) |
| `dnsp_essential.yaml` v0.2 | Research seeds | ES-R008 (HV documents), ESS-HV-001 (SCADA RTU for connection agreements signed from 2027-01-01), ES-001 (CERM1135 version check) |
| `dnsp_energex` / `dnsp_ergon` v0.2 | Research seeds (HV only) | Shared `shared_qld_stnw1175.yaml`: QLD-HV-001–005 from STNW1175 R6. The EMT model is required only for class A2 when no exception applies; guard QLD-HV-001X asks for class and exceptions first. LV (STNW1174) not read yet |
| `as_nzs_4777_2`, `cec_inverters` | Unverified | Licensed standard / sample list; use citations only |

Every technical value with no source (protection thresholds, region settings, export limits for non-Ausgrid DNSPs) is `null`.

The rule engine (`gridease/rules/engine.py`) is declarative: conditions live in YAML and the engine keeps kW, kVA and kWh as
separate fields. The NER pathway uses generation kW plus registration status, while protection uses aggregate inverter kVA.
Fired rules appear as compliance findings that carry their citation.

Values that have not been sourced are `null`. The platform reports them as unknown and never invents a default. A final
package stays blocked until the DNSP pack is `verified: true`.

- Source registries: `gridease/rules/sources/nsw_sources.yaml` (SRC001–016) and `dnsp_evidence_v04.yaml` (evidence sources, PDF manifest, canonical field vocabulary → parameter mapping), served at `GET /api/sources`
- Research backlog and data-master mapping: [`docs/rule-research-backlog.md`](docs/rule-research-backlog.md)
- Rule test cases from the workbook (T01–T05): `tests/test_rule_engine.py`
- Evaluate rules on raw fields: `POST /api/rules/evaluate`; for a project: `GET /api/projects/{id}/rules`

## Next steps

1. Collect the real application forms and technical standards from the NSW/QLD DNSPs and verify the rule packs.
2. Add an LLM extractor hosted in Australia, with PDF upload for bills and datasheets (including phone photos).
3. Measure SLD coverage by back-testing on design partners' real projects.
4. Support 8760-hour load data and real tariff structures, including demand charges.
5. Add users, organisations and permissions, audit log export, and deployment to the Sydney region.


## Internal workflow improvements

- Creating a project with a brief automatically generates a draft SLD. Saving design inputs,
  editing parameters, recalculating, or adding brief information regenerates it.
- The **Design inputs** form accepts site/network details and multiple PV inverter/battery rows.
  Save the whole form in one operation; invalid fields leave the saved project unchanged.
- **Single line diagram** shows a preview, engineer review checklist, and SVG download.
  Missing values remain TBC. Unsupported or incomplete inputs show actionable messages.
- Missing battery energy remains unknown; a battery-only project can still calculate PCS capacity.
  HV transformer secondary voltage and vector group are TBC rather than assumed values.
- Generation failures remain visible. Battery economics requires actual load and tariff inputs.
- File writes are atomic and revision checked. Concurrent writes return HTTP 409 instead of
  silently replacing another employee's changes. The browser includes its loaded project
  revision on mutations; use **Reload project** before retrying a conflict.
- Final ZIP export requires every document, current versions, resolved review items, and valid
  sign-offs in addition to the original rules and assumption gates.

### Deployment scope

This remains an internal development/trial application. It has no employee authentication,
role permissions, or managed backups yet. Do not expose the API directly to untrusted networks.
DNSP rule packs remain research seeds and require engineering verification before formal use.
The SLD generator supports the four documented topologies; it produces SVG drafts rather than
construction-certified CAD drawings. Validate actual installation topology and equipment data.

Run `.venv/bin/python -m pytest -q` for the regression suite. Browser smoke validation covers
creation, automatic SLD preview, design edits, automatic regeneration, download, invalid-input
recovery, partial document generation errors, and desktop/mobile layout.
