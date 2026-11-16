# Diagnostic review: actual runs 94-96

Result: NOT ACCEPTED for semantic quality. Read-only inspection; graph and model outputs were not edited. This is not a gold evaluation and contains no claimed accuracy percentage.

## Scope and source records

Raw export SHA256: f8d48b3c1e9b55818c0f73905b2e90a3dc640b8f8e7b22a67c172151853de3c5

- Run 94 (TWIN): 211 entity spans; 124 identity mentions; 117 canonical identities; 8 linked mentions; 116 unresolved mentions. Neo4j counts match the saved run.
  Source: documents/DigitalTwinSoftware_en.pdf; SHA256 59fd1207daada80d14d5bb6f80a6776687b519b80afed63174c3d06dbec373a8.
  Reading: 0 accepted links / 100 evaluated pairs. Semantic relations: 1; cross-source: 0.
  Placeholder entity spans: 17.
  Source warning: Visual-region OCR incomplete on pages: 1, 2. Readable text retained; failed requests retry on rerun, unreadable crops remain marked.
- Run 95 (BOX): 172 entity spans; 89 identity mentions; 78 canonical identities; 14 linked mentions; 75 unresolved mentions. Neo4j counts match the saved run.
  Source: documents/RC8_Controller_Protective_Box_Light_E.pdf; SHA256 212c2aea490ac67d82bbead0281dd52ff70793f3573e65359f71a86f747e8db8.
  Reading: 0 accepted links / 92 evaluated pairs. Semantic relations: 1; cross-source: 0.
  Placeholder entity spans: 19.
  Source warning: Visual-region OCR incomplete on pages: 1, 2. Readable text retained; failed requests retry on rerun, unreadable crops remain marked.
- Run 96 (PLUG): 275 entity spans; 97 identity mentions; 93 canonical identities; 5 linked mentions; 92 unresolved mentions. Neo4j counts match the saved run.
  Source: documents/New folder/Spark Plug Installation _ DENSO Auto Parts.pdf; SHA256 2e4ba8f98dd3bea2d6ae4425860999539589bdc904e060c571a5bbb6c2abad6b.
  Reading: 0 accepted links / 231 evaluated pairs. Semantic relations: 2; cross-source: 0.
  Placeholder entity spans: 30.
  Source warning: Visual-region OCR incomplete on pages: 1, 3, 4. Readable text retained; failed requests retry on rerun, unreadable crops remain marked.

## Confirmed issues

### critical: False identity merges

- Run94: Digital Twin Software, Unity and Realvirtual.io Professional share a canonical identity despite the PDF describing components/add-on relationships.
- Run95: RC8 Controller Protective Box Light, original RC8 Controller Protective Box, robot controller and RC8 type controllers share a canonical identity.
- Run96: First Time Fit, Iridium Power, Platinum TT and Iridium TT share a canonical identity.

### high: Entity type errors

- Run95 block:9728:1:0: RC8 tagged CONTRACT_NUMBER although it names a controller.
- Run95 block:9742:1:0: postal code 90810 tagged TAX_CODE.
- Run94 block:9706:1:0: document publication code SO-DTS-E 202502 tagged TAX_CODE.

### high: Generated image display labels passed into NER

- 66 entity spans across the three runs originate from figure placeholders whose ocr_status is skipped. These labels are UI metadata, not OCR text from the PDF.

### high: Reading model did not establish reading flow

- All 423 candidate decisions are unresolved; accepted reading links are zero in each run. Complete records processing must not be interpreted as successful semantic reading reconstruction.

### high: Semantic relation extraction insufficient

- Only four semantic relations and zero cross-source relations across these three runs.
- Run96 Step1 references above points to the word above, not its antecedent source.
- Scope quotations retain conditions, but condition_quotes, polarity and modality were not separately extracted for the inspected relations.

## What is working and what it does not prove

- Neo4j contains the canonical links recorded by the resolver: merging is persisted, not merely a display change.
- Every inspected entity span matches its stored source substring. This does not establish that the substring is genuine OCR, correctly typed, or correctly merged.
- Some repeated Unity occurrences represent the same product, and the BOX applies_to VM Series relation is supported by the quoted footnote. The larger merged groups still include distinct products.
- Model confidence can exceed 0.97 on incorrect identity pairs. A confidence threshold and successful unit tests do not establish semantic accuracy.

## Runtime failure

Run97 stopped after page3 with OSError: [Errno 12] Cannot allocate memory, HTTP500. The batch client stopped; 20 documents have not completed. No new graph was published for the incomplete run.

## Recommended correction order

1. Separate real source text from generated UI/image placeholders before model calls, using provenance metadata rather than keyword/regex semantic decisions.
2. Validate or train the same-entity model with real reviewed positive and negative source pairs, including component-vs-system, Light-vs-original, and different spark-plug models. Preserve the failing outputs.
3. Validate reading-flow and relation models on real source-linked examples; expose unresolved as unresolved in readiness reporting.
4. Diagnose resource failure and repeat through the existing HTTP pipeline only after the semantic issues are addressed.

Full evidence: quality_audit_runs94_96_raw.json and quality_audit_runs94_96.json.
