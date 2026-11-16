# Risk-reading skill for the contract risk analysis

The goal is a skill, not legal knowledge: read a contract clause and the provisions supplied in the brief, decide
whether the clause breaks a mandatory rule that a supplied provision states, and quote both texts. Finding the law is
not trained: the provisions come from the knowledge base search at run time, so an amended law needs a new extraction,
not a new model.

To make the model read the supplied law instead of remembering it, the data pairs numeric clauses with a
"changed-law twin": the same clause under a provision whose limit is moved across the clause's value, so the label
flips. Provisions where the parties may agree otherwise, vague clauses (drafting suggestions) and provisions that
govern nothing here are mixed in. Labels follow from the generated values, so they are right by construction.

## What a brief holds (as at run time)
- **The risk catalog**, always listed as the service lists it: the administrator's rules (`INTEREST_CAP`,
  `PENALTY_CAP`, `DEADLINE`, …), sometimes only some of them, sometimes the same kinds under made-up codes and other
  words (so a rule is matched by what it says, not by a code learned by heart), now and then empty. A risk takes the
  code of the rule that describes it, or `OTHER` when no listed rule does.
- **1 to 6 provisions**: the governing one(s), provisions on the same subject that set no rule the clause can break
  (they have to be read to be told apart), and provisions on other subjects. Provisions of one subject's sibling
  topics (a capped penalty next to "the parties agree the penalty") never sit together, as either could govern.
- **Other clauses of the contract** in about 40% of briefs; in cross-clause samples two clauses disagree on one amount
  or deadline (a drafting risk naming the other clause in `related_clause_ids`, filed under `CROSS_CLAUSE`); with equal
  values the pair is consistent and nothing is reported.
- **Two risks in one clause** in some samples (two sentences on two topics of the same kind of contract).
- **Vague clauses on eight subjects** (payment, price, delivery, quality, acceptance, compensation, price adjustment,
  terms left "to be agreed later"), each next to a provision that leaves the matter to the parties. The same provisions
  also come with clauses that settle the matter (fine, nothing to report). The label depends on reading the clause
  (settled or left open) and the provision (mandatory or agreed-otherwise), not on knowing the law: a vague clause is a
  drafting suggestion, never a legal conflict.

## Wording, splits and real law (data version 2)
- **Many wordings.** Each topic has about 10 clause wordings and 6 provision wordings (`CLAUSE_VARIANTS`,
  `LAW_VARIANTS`, `RULED_VARIANTS`, `UNCLEAR_VARIANTS`, `DEFAULT_VARIANTS` in `families.py`), plus opening phrases.
  Explanations and fixes have several forms too, so the model learns the reading, not a sentence.
- **Held-out wordings.** `Maker.pick` cuts every wording list: most go to training, the last ones only to the
  validation set or only to the evaluation set. About 10–12% of validation and evaluation clauses share a wording with
  training (they were 100% and 81%), so validation loss and evaluation scores measure unseen wordings.
- **Holdout topics of every kind**: ceilings, a ban, an agreed-otherwise provision (`complaint_terms`), vague clauses
  (`rent_vague`, `scope_vague`) and a cross-clause pair (`rent_price_twice`) appear only in the evaluation set.
- **Real law** (`build.REAL_LAW`): seven articles of the knowledge base. Training uses BLDS 468, 260, 454 and
  LTM 301, 222; the evaluation adds LTM 231, 199 and 318, never trained on. BLDS 454 and LTM 318 leave the matter
  to the parties, so they are real "no risk" examples. A law quote is the article's own sentence exactly as written
  (line breaks kept).
- **Catalog**: rules for labour terms, advances and vague terms were added, so OTHER covers about a fifth of the risks
  (topics whose rule is missing from a partial catalog), not half.

## Data version 3: what the run time really supplies
- **Governing provision absent** (`group: absent`, ~5%): retrieval missed it; only same-subject provisions that set no
  rule and other subjects are supplied, so no legal risk may be reported. Evaluated as `governing_absent`.
- **Amended law** (`group: amended`, ~6%): the original article, partly repealed with the run time's note
  ("Tình trạng: Hết hiệu lực một phần … Đã được sửa đổi hoặc bổ sung bởi: …"), next to the amending article (in force)
  with another limit; the clause value lies between the two, so the answer must follow the amending one. Evaluated as
  `amended_law`. A law turned off on the admin page ("Hết hiệu lực") is never searched, so no sample holds one.
- **Statuses** are written as `knowledge_repository.legal_note` writes them (in force, partly repealed, user upload).
- **Long articles** (`LONG_ARTICLE_SHARE`, also for other-subject provisions): 4–14 numbered paragraphs up to ~2,300
  characters; the quote is the rule's paragraph only (quotes that are ≥90% of the article fell from 92% to 44%).
- **Parties**: the parties line often names each side's role ("Bên A (Bên vay): …"), and the disadvantaged party is
  answered by role and name; the risk level follows how far the value is off the limit (`numeric_level`).
- **Evaluation real law** uses only articles never trained on (LTM 231, 199, 318).

## Data version 4 and the second training run
The first adapter (data v3, one epoch, learning rate 1e-4) found 54/113 conflicts against the base model's 107/113,
while its false legal risks fell from 105/149 to 30/149. Most misses copied the governing provision word for word but
named another L-number, so the quote check rejected them; it also found none of the two-risk clauses.
- **Provision positions**: briefs hold more provisions (`LAW_COUNTS`), and in half of the one-governing briefs the
  governing provision moves to a later position; governing at L1 fell from 34% to 20% of conflicts, L4-L6 rose from
  18% to 31%.
- **Two-risk clauses**: weight 11 -> 17 (146 -> 225 in training).
- **Size**: `--train 2200 --real` (2,475 rows), so two epochs fit a Kaggle session.
- **Evaluation set unchanged**: `data/eval.jsonl` is the v3 set (v3 data kept in `data/v3/`), so scores compare.
- **Notebook**: two epochs, learning rate 2e-4, evaluation on 60 valid briefs every 100 steps, `MAX_LEN` 4,352; the
  quick check (cell 6) now counts the right L-number and a word-for-word law quote, which the first check missed.
- **Service**: `clause_risk_service.attribute` files a risk under the one provision that holds its law quote.

## Files
- `families.py`: the topics (ceilings, floors, agreed-otherwise rules, mandatory forms, bans, vague clauses), the risk
  catalog kinds (`CONCEPTS`, `CONCEPT_OF`), same-subject provisions (`HARD`), clause pairs that disagree (`CROSS`),
  topic pairs for two-risk clauses (`COMBOS`) and the sample maker. `HOLDOUT` topics only appear in the evaluation set.
- `build.py`: writes `data/train.jsonl`, `data/valid.jsonl`, `data/eval.jsonl` (and prints, per split, the labels,
  risks with a catalog code, two-risk clauses and provisions per brief). Briefs and schemas come from
  `legal_ai.services.clause_risk_service`, so training matches inference; every target passes the service's own quote
  checks. `--real` adds samples on real provisions from the knowledge base (BLDS Điều 468, Luật Thương mại Điều 301)
  with their numbers moved.
- `evaluate.py`: replays each evaluation brief (same catalog, provisions and related clauses) through `review_clause`
  against the served model and reports conflict recall, false legal risks, vague clauses reported as suggestions,
  changed-law twins answered right, two-risk clauses, cross-clause risks, rule codes, and the holdout topics.
- `data/risk-skill-data.zip`: `train.jsonl` and `valid.jsonl`, to upload as the Kaggle dataset `risk-skill-data`.
- `data/eval_results_qwen3-8b-base_v1-data.json`: the base model on the first data version (no catalog in most briefs,
  one risk per clause); not comparable with the current evaluation set.

## Steps
```
docker exec riskdl_web python -m ai.training.risk_skill.build --train 2600 --real
docker exec riskdl_web python -m ai.training.risk_skill.evaluate --label qwen3-8b-base
# train a LoRA on data/train.jsonl (Kaggle notebook), serve it, then:
docker exec riskdl_web python -m ai.training.risk_skill.evaluate --label qwen3-8b-lora
```
A record: `messages` (system + user brief), `schema` (the JSON schema the server enforces), `target` (the answer to
learn), `expect` (what the evaluation checks), and `clause`, `related`, `rules`, `laws`, `parties` to replay the brief.
The longest brief with its answer is about 2,500 tokens, inside the notebook's 4,096.
