# Rule research backlog

Imported on 2026-10-17 from `GridEasy_Ausgrid_Rule_Pack_v0.2.xlsx` and `GridEasy_NSW_Data_Master_v0.1.xlsx`.
Rules stay **research seeds** (`verified: false`) until the P0 items below are done and an engineer signs off the rule version.

## Ausgrid rule pack v0.2 — backlog

| Priority | Task | Source | Output | Status |
|---|---|---|---|---|
| P0 | Read complete Non-Registered EG guideline and extract process gates | A02 | Workflow states and submission artifacts | Pending |
| P0 | Review full NS194 incl annexes and exemptions | A03 | Clause-level decision tables | Pending |
| P0 | Verify exact 200kW / 200kVA / 5MW / 5MVA boundaries per connection category | A01;A02;A03 | Boundary test matrix | Pending |
| P0 | Get current application form and required attachments | A04 | Field mappings and packet templates | Pending |
| P0 | Engineering review of 10 seed rules | A01–A09 | Approved rule version | Pending |
| P1 | Collect NS195 HV and ES1 cross-references | A05;A06 | HV branch | Pending |
| P1 | Verify new late-2026 NSW Emergency Backstop dates | A08;A09 | Effective-date gating | Pending |
| P1 | Obtain licensed standards and map citations only | AS/NZS | Licensed standard metadata | Pending |
| P1 | Build Endeavour rule pack from official sources | Endeavour | Same schema, distinct jurisdiction rules | Pending |
| P1 | Build Essential rule pack from official sources | Essential | Same schema, distinct jurisdiction rules | Pending |

## NSW data acquisition backlog

| Priority | Owner / source | Task | Source ID | Status |
|---|---|---|---|---|
| P0 | AEMO | Capture guideline clauses and applicability | SRC002 | Pending |
| P0 | Ausgrid | Capture >200kVA application checklist and templates | SRC004 | Pending |
| P0 | Endeavour | Find current EG technical standard, forms and process | SRC007 | Pending |
| P0 | Essential | Acquire CEOP8079, CERM1135, CEOS7903, CEOP8012 | SRC008 | Pending |
| P0 | NER | Fetch latest Chapter 5A and registration exemptions | SRC013 | Pending |
| P0 | Standards | License applicable AS/NZS documents and record editions | SRC011 | Blocked by licence |
| P0 | Project examples | Get 3–5 consented historical project packs | SRC016 | Blocked by customer |
| P1 | CEC/OEM | Approved equipment lists and datasheets | SRC015 | Pending |
| P1 | NSW | Verify emergency backstop implementation and scope | SRC014 | Pending |
| P1 | Engineering | Build 20 expert-reviewed test cases for first DNSP | SRC016 | Blocked by engineer |

## Data Master rule seeds → where they live in code

| Data Master | Implemented as |
|---|---|
| R001 Ausgrid >30–200 kVA pathway | AG-R011 export option; pathway itself pending form/checklist |
| R002 Ausgrid >200 kVA – 5 MVA | AG-R002 / AG-R003 |
| R003 Ausgrid non-registered 200 kW–5 MW | AG-R001 |
| R004 Ausgrid three-phase >30–200 kVA export | AG-R011 (`export.default_static_limit_kw: 30`) |
| R005 AEMO sub-5 MW guideline (advisory) | AG-R013 |
| R006 Ausgrid equipment conformity | AG-R012 + CEC checks |
| R007 NSW emergency backstop | AG-R009 |
| R008 Essential HV | ES-R008 (document retrieval only — not executable) |

## Rules on the rule packs

- kW (generation, export), kVA (inverter/PCS apparent power) and kWh (battery energy) are separate fields. The NER pathway uses kW plus registration status; Ausgrid interface protection uses aggregate inverter kVA.
- A rule pack value that has not been sourced is `null`; the platform reports it as unknown and never substitutes a default.
- AS/NZS standards need a licence: store citations and edition metadata only.
- Customer project packs need consent/NDA before being used as test cases.

## DNSP Evidence Pack v0.4 — backlog

| Priority | DNSP | Task | Status | Approval needed |
|---|---|---|---|---|
| P0 | Ausgrid | NS194 Rev5 full clause-by-clause and 2023 diff | pending_pdf_local | engineering review |
| P0 | Endeavour | PDI5000 A/B detailed clause extraction | pdf_web_available | engineering review |
| P0 | Essential | CEOP8079 controlled PDF and CERM1135 latest | index_confirmed | manual download/version check |
| P0 | Energex/Ergon | STNW1175 sections 6 Appendix D E and A2 checklist | pdf_web_available | engineering review |
| P0 | All | AS/NZS commercial reuse rights | purchase_required | legal/licensing review |
| P1 | All | DNSP terms of use for systematic extraction and redistribution | not_verified | legal review |
| P1 | All | model/commissioning verification cases | not_collected | qualified engineer |

## Evidence Pack v0.4 / Source Links v0.3 → where they live in code

| Source rule | Implemented as | Pack |
|---|---|---|
| AG-001, AG-002 (NS194 Rev5 1.1.4, 1.3.1) | AG-001, AG-002 | `dnsp_ausgrid.yaml` v0.3 |
| AUS-EB-001…004 (Emergency Backstop) | AUS-EB-001…004, keyed on `commissioning_date` / `dnsp_approval_date`; unknown date ⇒ rule fires for review | `dnsp_ausgrid.yaml` v0.3 |
| EE-001…003 (PDI 5000 am6 Part A) | EE-001…003 | `dnsp_endeavour.yaml` v0.2 |
| ESS-HV-001 (SCADA from 2027-01-01), ES-001 (CERM1135 version) | ESS-HV-001, ES-001 | `dnsp_essential.yaml` v0.2 |
| QLD-HV-001…005, QLD-001/002 (STNW1175 R6) | QLD-HV-001…005 + guard QLD-HV-001X; QLD-001/002 merged into QLD-HV-004 | `shared_qld_stnw1175.yaml` (Energex + Ergon) |

## Known gaps (not implemented on purpose)

- Ausgrid backstop **postcode stage list** and **exemptions**: not in the evidence; AUS-EB-002 asks for a manual postcode check.
- NS194 clause numbers in AG-R002/R003/R006 come from an earlier revision; re-check against Rev5 (2026-09-10).
- Energex/Ergon **LV** (STNW1174) not read; QLD LV projects show a `rules.coverage_gap` finding.
- "Very low SCR" (QLD-HV-002) uses SCR < 3 as the indicative threshold given in the evidence.
- Legal: DNSP terms of use for systematic extraction/redistribution and AS/NZS reuse rights are unverified (P0/P1 above).
