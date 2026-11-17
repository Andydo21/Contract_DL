# legal_kb

Vietnamese law split into articles and clauses, in the core Postgres, each document with the dates it applies.
The AI looks provisions up here and cites them; it is not expected to know the law itself.

## Source

[`th1nhng0/vietnamese-legal-documents`](https://huggingface.co/datasets/th1nhng0/vietnamese-legal-documents)
(CC BY 4.0), a crawl of vbpl.vn (Ministry of Justice), pinned to one revision in the manifest. vbpl.vn and
thuvienphapluat.vn refuse automated requests, so the portal itself is not read.

`sources/<domain>.json` lists the documents of a domain by vbpl id. vbpl's own "guides" links miss most
guidance documents (145/2020/NĐ-CP is not linked to the Labour Code), so the list is kept by hand. An entry may
override vbpl's dates and status (`effective_from`, `effective_to`, `status` with `status_note`) and record known
missing text (`gaps`).

`labour` holds 32 documents: the Labour Code, the social insurance, employment, occupational safety and trade
union laws, with their decrees and circulars, plus the versions replaced in 2025–2026 (Luật BHXH 2014, Luật Việc
làm 2013, 74/2024/NĐ-CP) for questions about earlier dates.

## Import

```
python manage.py import_laws [--domain labour] [--data-dir DIR] [--force]
docker compose -f docker-compose.core.yml run --rm web python manage.py import_laws
```

The first run downloads the three dataset files (~800 MB) to `LEGAL_KB_DATA_DIR` (default `media/legal_kb`). A
document whose text has not changed is not parsed again; documents dropped from the manifest are removed.

- `parser.py` reads vbpl's `prov-chapter / prov-section / prov-article / prov-clause / prov-item` markers, or the
  text ("Điều 5.", "1.", "a)") when they are missing. A provision is a clause with its points, or an article's text
  before clause 1. Tables become rows with cells joined by ` | `. The signature block is dropped; appendices that
  are in the HTML are kept in parts of about 2,500 characters.
- vbpl's links between documents are stored as "actor effect subject" (`amends`, `replaces`, `repeals`, `ends`,
  `ends_part`, `supplements`, `guides`, …), including links from documents outside the corpus.
- The report lists, per document, articles missing from the numbering and appendices that are cited but absent.

## Lookup

| Endpoint (login required) | |
| --- | --- |
| `GET /api/legal/search/?q=&date=YYYY-MM-DD&limit=` | best clause per article, from documents in force on `date` (default today) |
| `GET /api/legal/article/?doc=45/2019/QH14&article=25&date=` | every clause of one article |
| `GET /api/legal/documents/?date=` | the corpus, with status, warnings and whether each document is in force |

Every result carries the document's dates and status, `gaps`, and `changed_by`: the documents that amended,
replaced or partly ended it by `date`. vbpl records these per document, not per clause, so a result with
`changed_by` may be out of date and the changing document should be checked.

Search: the full-text index (`simple` config, text indexed with and without diacritics) selects clauses holding
any less common query word, then BM25 over syllables and syllable pairs ranks them, the article heading counting
four times. `python manage.py eval_laws` scores it on `sources/labour_eval.json` (21 questions): 19 have the
expected article in the top 5, 14 at rank 1. Misses are synonyms the law does not use ("nghỉ phép năm" for
"nghỉ hằng năm"), which needs semantic search.

## Known gaps in the source

- Appendices published only as PDF are missing in 19 documents, including the list of minimum wage regions in
  293/2025/NĐ-CP, the forms of 145/2020/NĐ-CP and the job list of 06/2020/TT-BLĐTBXH.
- Article 38 of 41/2024/QH15 and article 10 of 105/2026/NĐ-CP are missing from vbpl's HTML.
- vbpl marks 41/2024/QH15 as wholly expired from 01/01/2026; the manifest keeps it in force (only part was
  replaced by the 2025 Employment Law).
- Amendments are not merged into the amended text; consolidated texts (văn bản hợp nhất) are not imported.

## Tests

```
python manage.py test legal_kb      # needs Postgres (tsvector, GIN)
```
