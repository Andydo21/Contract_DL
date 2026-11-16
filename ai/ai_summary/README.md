# ai_summary

Django app `ai.ai_summary` (same layout as `ai_extract`): source-verified Vietnamese contract summaries from the
served text model (Qwen on Kaggle, `VLLM_BASE_URL`). It runs inside the web app, no separate container.

```
ai/ai_summary/
  views/summary_views.py     HTTP endpoints (login required, errors -> 400/422/502)
  services/summary_service.py   pipeline: chunk, parallel model calls, merge, verify, render, compare, cache
  services/llm_service.py       OpenAI-compatible client of the served model
  services/reader_service.py    PDF / DOCX / TXT reading (OCR of scanned pages with Tesseract when installed)
  services/text_service.py      sections, facts, chunking, numbers
  services/legal_service.py     labour-contract checklist, glossary
  services/insights_service.py  preliminary facts and suggestions without a model call
  schemas.py                    request models and the JSON schema the model must follow
  tests/                        unit tests (no network, no database)
  tools/                        evaluation set, Kaggle notebook, fine-tuning scripts (run by hand)
```

A contract's summary (`POST /api/ai/contracts/<id>/summarize/`, "Tóm tắt" tab) goes through this pipeline:
`ai_extract.services.extraction_service.SummarizeService.summarize_version` joins the version's clauses, calls
`summary_service.summarize` and stores the rendered text in `ContractSummary`.

| Endpoint (login required) | |
| --- | --- |
| `POST /api/ai/summary/summarize-file/` | multipart `file` + `perspective`, `length`, `explain_terms`, `force`, `model`, `contract_metadata` (JSON); result + `source` (kind, pages, OCR'd pages, warnings) |
| `POST /api/ai/summary/compare-files/` | `old_file`, `new_file` + the same options |
| `POST /api/ai/summary/read/` | text read from a file and its chunk plan; no model call |
| `POST /api/ai/summary/sections/` | clause text by label ("Điều 3"); no model call |
| `POST /api/ai/summary/summarize/`, `/compare/`, `/prepare/` | the same on plain text (JSON) |
| `GET /api/ai/summary/health/` | model reachable, analysis version, OCR available (no login) |

## Reading files (`reader.py`)

- PDF: PyMuPDF text layer in reading order; pages with no text layer (scans) are OCR'd with Tesseract
  `vie+eng` at 300 dpi (installed in the Docker image; `/health` reports `ocr_available`).
- DOCX: paragraphs and tables in document order, table cells joined with ` | `.
- TXT: UTF-8 (or UTF-16 with BOM; otherwise Windows-1258).
- The content decides the format, not the file name. Old `.doc`, password-protected or empty files get a
  clear 422 message. Limits: `SUMMARY_MAX_FILE_MB` (25), `SUMMARY_MAX_OCR_PAGES` (60).

| Endpoint | |
| --- | --- |
| `POST /api/v1/summarize-file` | multipart `file` + `perspective`, `length`, `explain_terms`, `force`, `model`, `contract_metadata` (JSON); result + `source` (kind, pages, OCR'd pages, warnings) |
| `POST /api/v1/compare-files` | `old_file`, `new_file` + the same options |
| `POST /api/v1/read` | text read from a file and its chunk plan; no model call |
| `POST /api/v1/summarize`, `/compare`, `/prepare` | the same on plain text (JSON) |

## Pipeline

1. `text_tools.split_sections` — split on `Điều N` / `Article N` headings (`S0` = preamble with the parties).
2. `text_tools.extract_facts` — regex-copied money, dates, durations, %, tax codes, parties. Sent to the model as anchors.
3. `text_tools.chunk_sections` — whole sections packed into chunks of `SUMMARY_CHUNK_CHARS`; above
   `SUMMARY_MAX_CHUNKS` the preamble and value/payment/term/penalty/termination sections are kept first.
4. One schema-constrained call per chunk (`schemas.SUMMARY_SCHEMA`), run in parallel; vLLM batches them
   and reuses the shared system-prompt prefix. Token logprobs are requested for confidence.
5. Merge in code (no extra model call), then verify (`services._verify`):
   - values whose numbers are absent from the source, injected instructions, payment/delivery deadlines
     given as the contract term, non-termination text under termination, uncited or repeated risks are dropped;
   - tax code and representative are read from each party's own block of the source, never from the model;
   - the effective date and the term fall back to the source sentence that states them.
   Every dropped value is returned in `unverified` with its reason.
6. Confidence per field (`structured.confidence`, list items' `confidence`): lowest and mean token
   probability plus the share of the value's words found in the source; low ones get "⚠ cần kiểm tra".
7. Labour contracts get the Article 21(1) BLLĐ 2019 checklist (`legal.py`, keyword match with the clause cited).
8. Render text from the verified JSON (`services.render`): perspective `general` / `employee` / `hr`,
   length `detailed` / `short` / `one_sentence`, optional plain-language glossary (`legal.GLOSSARY`).

`analyze` results are cached by `sha256(prompt version + model + text)` in memory and in `SUMMARY_CACHE_DIR`,
so changing perspective, length or glossary never calls the model again; send `force: true` to regenerate.

`POST /api/v1/compare` analyses two versions (each cached) and reports only field changes whose source
clause actually changed, with amounts and durations computed in code ("tăng từ X lên Y (+Z)", "gia hạn thêm 12 tháng").

## Configuration

| Variable | Default |
| --- | --- |
| `SUMMARY_LLM_URL` (falls back to `VLLM_BASE_URL`) | — |
| `SUMMARY_MODEL_ID` | `phamthanhfd/contract-summary-qwen3-1.7b` |
| `SUMMARY_CHUNK_CHARS` / `SUMMARY_MAX_CHUNKS` | `9000` / `16` |
| `SUMMARY_PARALLEL` / `SUMMARY_MAX_TOKENS` / `SUMMARY_LLM_TIMEOUT` | `4` / `1500` / `180` |
| `SUMMARY_LOGPROBS` / `SUMMARY_LOW_TOKEN_PROB` / `SUMMARY_LOW_MEAN_PROB` | `1` / `0.3` / `0.7` |
| `SUMMARY_MAX_FILE_MB` / `SUMMARY_MAX_OCR_PAGES` / `SUMMARY_OCR_LANGUAGES` | `25` / `60` / `vie+eng` |
| `SUMMARY_CACHE_DIR` | the system temp folder (`ai_summary_cache`) |

Settings come from the root `.env`; with no `SUMMARY_*` values the app uses `VLLM_BASE_URL` and `QWEN_MODEL_ID`.

`tools/kaggle_notebook.py` Cell 2 starts the main model (GPU 0) and an optional candidate (GPU 1) in parallel
behind one proxy and URL; requests choose a model by `model`. Cell 4 swaps only the candidate.

## Tests and evaluation

```
python manage.py test ai.ai_summary --settings=config.sqlite_test_settings
python ai/ai_summary/tools/eval_summary.py                      # golden set against the running web app
python ai/ai_summary/tools/eval_summary.py --model <served id>  # same set against a candidate model
```

## Fine-tuning a smaller model

1. `python ai/ai_summary/tools/finetune/make_dataset.py --count 2400` writes `tools/finetune/data/{train,dev}.jsonl`: synthetic
   contracts (sale, service, construction, lease, labour, MOU, English, no-heading, OCR noise, injected
   instructions, multi-chunk) whose labels are copied from the clauses, so they are exact by construction.
   Prompts go through the production chunking and `_user_prompt`.
2. Upload the two files as a Kaggle Dataset and run `tools/finetune/train_kaggle.py` (LoRA, merge, push to HF).
3. Serve the pushed repo as the candidate (Cell 4 of `tools/kaggle_notebook.py`) and run
   `tools/eval_summary.py --model <repo>`; switch `SUMMARY_MODEL_ID` only if the golden set does not regress.
