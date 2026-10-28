# ai_summary

Standalone contract summary service. Django (`POST /api/ai/contracts/<id>/summarize/`) sends the version's
OCR text from `ai_extract` and stores the returned text in `ContractSummary`; all prompts, model choice and
caching live here. `/ai-extract/summary-lab/` is the test screen.

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
| `SUMMARY_CHUNK_CHARS` / `SUMMARY_MAX_CHUNKS` | `18000` / `8` |
| `SUMMARY_PARALLEL` / `SUMMARY_MAX_TOKENS` / `SUMMARY_LLM_TIMEOUT` | `4` / `1500` / `180` |
| `SUMMARY_LOGPROBS` / `SUMMARY_LOW_TOKEN_PROB` / `SUMMARY_LOW_MEAN_PROB` | `1` / `0.3` / `0.7` |

`kaggle_notebook.py` Cell 2 starts the main model (GPU 0) and an optional candidate (GPU 1) in parallel
behind one proxy and URL; requests choose a model by `model`. Cell 4 swaps only the candidate.

## Tests and evaluation

```
cd ai_summary
python -m unittest test_summary test_features
python eval_summary.py                      # golden set against the running service
python eval_summary.py --model <served id>  # same set against a candidate model
```

## Fine-tuning a smaller model

1. `python finetune/make_dataset.py --count 2400` writes `finetune/data/{train,dev}.jsonl`: synthetic
   contracts (sale, service, construction, lease, labour, MOU, English, no-heading, OCR noise, injected
   instructions, multi-chunk) whose labels are copied from the clauses, so they are exact by construction.
   Prompts go through the production chunking and `_user_prompt`.
2. Upload the two files as a Kaggle Dataset and run `finetune/train_kaggle.py` (LoRA, merge, push to HF).
3. Serve the pushed repo as the candidate (Cell 4 of `kaggle_notebook.py`) and run
   `eval_summary.py --model <repo>`; switch `SUMMARY_MODEL_ID` only if the golden set does not regress.
