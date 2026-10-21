# A3 source and layout graph

A3: PNG -> Surya source regions -> source-label structure + GLiNER entities and
within-region relations -> BGE/ColPali indexing -> Neo4j. Qwen is used by A2 for
answers, never by A3 to construct relationships.

Structure uses model labels and explicit heading levels. Unknown levels remain
unknown. Model reading order and one text-only OCR pass inside images are kept.
No reference-number parser or generative excerpt-pair stage runs in ingestion.

## Relationships

- CONTAINS: source-backed parent/child structure and image contents.
- HAS_EVIDENCE: nodes linked to original source text and location.
- NEXT: model reading order within the same page/image scope, not same paragraph.
- HAS_VISUAL / APPEARS_IN: source text/blocks linked to page images.
- HAS_EMBEDDING: figure block linked to its acknowledged Qdrant point.
- HAS_ROW / HAS_CELL: native table structure and source values.
- MENTIONS: source text contains a GLiNER entity span.
- Typed semantic relationships: GLiNER proposals with source quotations.
- LEFT_OF / ABOVE / NEAR: supplementary geometry, not semantic support.

All semantic model proposals remain unreviewed after source validation. Each
snapshot is isolated by company, contract, version, run and source fingerprint.

A2 retrieves text and images, expands stored graph relationships and passes
prioritized, evidence-bound context to Qwen. Geometry has a small supplementary
budget. Source excerpts remain the evidence; graph links help navigate them.

## Reprocessing

    python manage.py sync_document_graph --run-id ID --analyze-relations

This explicitly reruns GLiNER on stored OCR, then synchronizes Neo4j. It does not
call Qwen, repeat OCR or regenerate embeddings. Ordinary synchronization needs
no model. Old document-pair metadata is ignored by projection and retrieval.
