# Relation diagnostic: PLUG, RACE, INSUL (runs101-103)

Read-only review of saved source/model outputs and actual Neo4j paths. The running batch was not changed. This is not a measured accuracy result.

## Findings

### PLUG - run101

- Stored NEXT edges: 104. Cross-snapshot: 0; cross-page: 0; cross-reading-stream: 0; reversed source reading rank: 0.
- Figure regions retained: 15. OCR child regions checked: 13; missing stored containment paths to their original parents: 0.
- GLiNER review: supported=0, disputed=0, unresolved=82, not_applicable=88. Invalid source-integrity checks=0.
- Distinct model input pairs: 71. Repeated input pairs can annotate more than one stored source edge.

### RACE - run102

- Stored NEXT edges: 96. Cross-snapshot: 0; cross-page: 0; cross-reading-stream: 0; reversed source reading rank: 0.
- Figure regions retained: 19. OCR child regions checked: 12; missing stored containment paths to their original parents: 0.
- GLiNER review: supported=0, disputed=0, unresolved=77, not_applicable=82. Invalid source-integrity checks=0.
- Distinct model input pairs: 61. Repeated input pairs can annotate more than one stored source edge.

### INSUL - run103

- Stored NEXT edges: 91. Cross-snapshot: 0; cross-page: 0; cross-reading-stream: 0; reversed source reading rank: 0.
- Figure regions retained: 16. OCR child regions checked: 27; missing stored containment paths to their original parents: 0.
- GLiNER review: supported=0, disputed=0, unresolved=58, not_applicable=106. Invalid source-integrity checks=0.
- Distinct model input pairs: 40. Repeated input pairs can annotate more than one stored source edge.

## Manual source checks and limitations

- PLUG page2: the stored reading chain follows increase-gap heading -> Step1 -> Step2 -> decrease-gap heading -> Step1 -> Step2. This matches the source order. It is not an inferred reference from the second Step1 to the word above.
- RACE page2: heading A (100% platinum ground electrode) links in reading order to its descriptive paragraph; heading B (self-cleaning spark) links to its own paragraph. Those inspected transitions match the PDF.
- INSUL page2: the heading for identifying plug numbers leads to the source table, then the plug-table heading. The original diagram contains numbered 1-12 and lettered A/B/C callouts. Source containment alone does not establish their meaning or connect them to model-table entries.
- RACE page2 has A-G callouts on the spark-plug picture. No EXPLAINS/typed semantic edges are stored to establish each callout-to-component-description mapping.
- NER is intentionally entities-only in this configuration; zero newly generated entity semantic relations is expected. The review task concerns the existing Surya NEXT/CONTAINS proposals.
- All 217 textual structural relation reviews remain unresolved. The model review adapter records only grounded scores >=0.9; stored supported=0/reverse=0 are filtered scores and do not establish that every raw model probability was zero. Raw rejected proposals are not saved, limiting diagnosis of the threshold versus model suitability.
- not_applicable means the text model lacked usable quotations on both sides, often because an image has no OCR text. The image and its source relations remain present.
- No structural cross-scope or missing-parent error was found in the checks above. Semantic correctness of all source relations is NOT verified.

## Traceable evidence

- quality_audit_runs101_102_103_raw.json: source excerpts, model decisions and stored relation counts.
- relations_runs101_102_103_checks.json: actual Neo4j NEXT checks and example source-to-source transitions.
- Raw export SHA256: be37973961aea33d732479d6d955781f697d8d0ec9ce1a59573f7127d9c58312.
