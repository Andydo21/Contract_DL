# Two-document HTTP extraction check: runs 98 and 100

Execution completed. Semantic quality is only partially satisfactory; do not treat graph readiness as model accuracy. This is a diagnostic review, not a gold evaluation.

## Execution

- TWIN: run98 completed through the project layout-extract API.
- BOX: run99 failed with PostgreSQL SSL EOF (HTTP500); the failed result was retained.
- BOX: run100 completed through the same API after adding a connection health check before starting a database write unit.
- ColPali was explicitly deferred. No third document was started.
- NER labels: PRODUCT, ORGANIZATION, PERSON, LOCATION. Threshold: 0.65. NER emits no new semantic relations.
- GLiNER reviews existing Surya relations before graph publication. Equal names are only merge candidates; GLiNER2 context approval is still required.

## Verified against stored results

### TWIN: run98

- Entities: 37; canonical identities: 37; linked mentions: 0; unresolved mentions: 8.
- Figure regions: 8; OCR child regions: 20; missing source parents: 0.
- Entity spans from generated image labels: 0; stored source-span mismatches: 0; mixed-name local canonical groups: 0.
- Original source order preserved: True; new GLiNER reading edges: 0.
- GLiNER relation review: {"disputed": 0, "integrity_checked": 263, "invalid": 0, "not_applicable": 52, "pending": 0, "supported": 0, "unresolved": 30}.
- Image/ownership relations HAS_VISUAL, APPEARS_IN, CONTAINS and HAS_EVIDENCE remain stored in Neo4j.
- Source warning: Visual-region OCR incomplete on pages: 1, 2. Readable text retained; failed requests retry on rerun, unreadable crops remain marked.


### BOX: run100

- Entities: 46; canonical identities: 42; linked mentions: 6; unresolved mentions: 16.
- Figure regions: 9; OCR child regions: 4; missing source parents: 0.
- Entity spans from generated image labels: 0; stored source-span mismatches: 0; mixed-name local canonical groups: 0.
- Original source order preserved: True; new GLiNER reading edges: 0.
- GLiNER relation review: {"disputed": 0, "integrity_checked": 247, "invalid": 0, "not_applicable": 34, "pending": 0, "supported": 0, "unresolved": 24}.
- Image/ownership relations HAS_VISUAL, APPEARS_IN, CONTAINS and HAS_EVIDENCE remain stored in Neo4j.
- Source warning: Visual-region OCR incomplete on pages: 1, 2. Readable text retained; failed requests retry on rerun, unreadable crops remain marked.

- Linked group: 5b8a0652-6d3a-5768-adf5-c232ded0b054; names: ["RC8 Controller Protective Box Light", "RC8 Controller Protective Box Light", "RC8 Controller Protective Box Light"]; source IDs: block:9992:1:0, block:10001:1:0, block:10010:1:0.
- Linked group: 7af3c739-738c-5d71-926e-15738748792c; names: ["RC8 Controller Protective Box", "RC8 Controller Protective Box", "RC8 Controller Protective Box"]; source IDs: block:9999:1:0, block:10001:1:0, block:10014:1:0.

## Remaining issues

- BOX correctly keeps Light and original RC8 boxes in separate canonical groups, with three matching occurrences in each.
- TWIN has no accepted merges; repeated Unity occurrences remain unresolved because one direction falls below the configured confidence threshold.
- NER still misclassifies publication codes (SO-DTS-E 202502 / P-CBL-E) and IP54 as PRODUCT. Removing numeric attribute labels alone does not solve semantic false positives. Generic category nouns are also extracted.
- GLiNER returns no supported/disputed semantic verdicts for the reviewed Surya relations: 30 unresolved in TWIN and 24 in BOX. The source relations are preserved and marked unresolved, not presented as verified.
- Both documents retain image OCR warnings on pages 1 and 2. Figure nodes still exist; OCR-skipped display labels are not used as entity evidence.

## Evidence

Raw source/model/Neo4j export: quality_audit_runs98_100_raw.json.
Machine-readable checks: quality_audit_runs98_100.json.
Raw export SHA256: 7f58a3a1445def9ac27e59109aae4cadec269d5432207a292cd584a7f0d23e0d.

No model outputs, citations, or existing metrics were edited to improve these results.
