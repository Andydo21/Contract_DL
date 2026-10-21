# CAD-export and SOP evidence checks

At `/newidea/`, select two extracted PDF/image-export documents and run the
comparison. `GET /api/newidea/spec-drift/` lists authorized latest extracted
versions; POST takes `cad_version_id` and `sop_version_id`. Both versions require
a completed A3 extraction and visibility to the current user. DWG/DXF/STEP
geometry is not processed.

The first implementation recognizes explicit labeled lines for material,
voltage, torque, diameter, length and pressure. It requires the same explicit
part number and one unambiguous value per field on each side. Compatible units
are converted using Decimal. Ranges, tolerances, decimal commas, missing IDs,
multiple values and unsupported fields remain unverified. Unlabeled drawing
dimensions and table grids are not covered by this matcher. It uses actual
extracted text; it does not ask Qwen to invent specifications or relations.

Differences are reviewer candidates, not proof of semantic contradiction. SOP
limits versus drawing nominal values can differ legitimately. Materials may
also have equivalent aliases; experts decide applicability and equivalence.
No result asserts zero hallucinations or complete document consistency.

Grounding uses stored original block IDs, normalized bbox and page image.
The source link opens `#block-ID`; the page inspector draws a red outline only
for that existing source box. This is block-level localization, not precise
word/value coordinates and not proof that OCR is correct. Missing boxes/images
produce `bbox_unavailable`, with no invented coordinates.

Duplicate checking hashes normalized extracted text (case/whitespace normalized),
not file bytes. Near duplicates use four-word shingle overlap; they are warnings,
not automatically removed or suppressed. Sparse text cannot prove duplication.

Company A2 discovery automatically checks at most six discovered versions.
Incomplete/truncated source sets skip automatic checks. Only five warning pairs
are shown, with partial coverage reported; this is not a whole-collection scan
or an upload-triggered background job. Explicit comparison remains available.
The search receipt records warnings for audit; source files are never rewritten.

Automatic findings are now connected to answer generation. Both source blocks
of a detected spec difference receive ordinary document citation IDs, preserved
whole so keyword windows cannot drop compared values. Comparison evidence is
prioritized within the bounded generation context; only findings with both
citations actually sent are included in the model instruction. Opinions retain
their separate source identity and applicability. Duplicate signals require
cited documents on both sides and must not be presented as independent proof.

Audit questions can be answered from these explicit comparison sources even
when generic audit wording does not overlap source keywords. This does not
bypass missing-number or unresolved-reference checks. Unavailable generation
continues to show source excerpts and separate warning cards. The manual
comparison panel is optional, not required for automatic company discovery.

80 focused tests passed after integration, including two-source model payloads,
review-only wording and refusal to invent numeric values in audit questions.
Model calls in tests are fixtures; no real CAD/SOP generation quality claim.

Validation: 78 focused tests passed, including tenant denial, anonymous requests,
unextracted documents, compatible/incompatible units, ambiguous subjects,
two-source bbox provenance, duplicate-text wording and discovery bounds.
This is behavior verification, not CAD/SOP accuracy evaluation on labeled data.
