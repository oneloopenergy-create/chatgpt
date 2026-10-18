# Uploaded AU / NZ SLD reference review

The two user archives contain **24 PDFs** (15 AU, 9 NZ), including drawings,
requirements, reports, historical maps and a draft guideline. This is a scoped
reference review, not model training or proof that all drawings meet current rules.
The packaged `gridease/sld/reference_catalog.json` records each original SHA-256,
page count, jurisdiction, category, reviewed pages and permitted use. Original PDFs
and customer/consultant drawings are not redistributed in this repository.

## Observations implemented

| Reference | Reviewed material | Result in GridEasy |
|---|---|---|
| AusNet 1500–5000 kW SLD example | p1: radial distribution, equipment/cable tables, title block | Top-down cable graph; fixed A3 landscape sheets; separate schedules |
| Jemena solar/battery SLD requirements | pp2–3,5–7: board names, existing/new plant, model counts, AC/DC examples | Extra named switchboards with phases and existing/new status; equipment per-unit kVA/kW and battery kWh retained in schedule |
| AusNet historical SLD requirements | pp2–5: drawing number, revision, designer/checker, readable electronic drawing | Editable drawing number/date/company/checker; vector print output |
| NZ Oakridge solar planning package | p11, E200: HV equipment, ownership demarcation, CT/VT, multiple inverter groups | Optional boundary tied to an explicitly selected cable; transformer and instrument identifiers stay linked to entered assets |

The physical topology comes only from project cables and transformer winding nodes.
Reversing a cable's endpoint order does not move it to the disconnected section.
Unconnected assets remain marked and block readiness; no feeder is silently added.
Breaker, isolator, transformer and converter endpoints have explicit geometry, so
cables terminate at the symbol rather than leaving a visible gap. Dashed instrument
leaders identify the **entered installation asset**, not a claimed secondary circuit.
Detailed secondary conductors remain in the separate protection schematic.

No NS194 Rev2, AusNet example, NZ planning stamp or draft guideline overrides the
reviewed project standard, approved settings or approval evidence. Transmission maps
are context only. Full NZ compliance and automatic conversion of arbitrary PDFs into
validated electrical networks are not implemented.

## Use

1. In 工程交付 → 工程数据表, enter drawing metadata and actual equipment/cables.
2. Add extra boards under 其他配电盘 / PVDB, then reference their IDs in cables.
3. If known, select the ownership-boundary cable ID; otherwise only the supplied
   boundary description appears. The software does not infer its physical position.
4. Save the engineering design to regenerate an existing project's SLD.
5. Preview SLD, then 打印 / 保存 PDF. Each sheet prints at A3 landscape with vector
   lines. The scoped release ZIP also includes `01_sld_A3_print.html`; open and print
   it to PDF. The SVG is retained as the source drawing. Check paper size in the
   target browser's print dialog.

Diagram labels abbreviate very long text; the separately paginated schedules retain
full equipment/model and cable specification values. Very large or meshed networks
still need engineering layout review. A recorded checker name is not a signature.

## Validation

Structural tests cover reversed cables, exact symbol terminals, extra/orphan boards,
reserved IDs, long labels, multi-sheet schedules, reference scope, and the A3 print
endpoint. A Chromium-generated PDF was checked for A3 landscape dimensions and
one page per drawing sheet. These are software/rendering checks, not project approval.
