# Risk-reading skill for the contract risk analysis

The goal is a skill, not legal knowledge: read a contract clause and the provisions supplied in the brief, decide
whether the clause breaks a mandatory rule that a supplied provision states, and quote both texts. The law itself comes
from the knowledge base at run time, so an amended law needs a new extraction, not a new model.

To make the model read the supplied law instead of remembering it, the data pairs every numeric clause with a
"changed-law twin": the same clause under a provision whose limit is moved across the clause's value, so the label
flips. Provisions where the parties may agree otherwise, vague clauses (drafting suggestions) and unrelated provisions
(distractors) are mixed in. Labels follow from the generated values, so they are right by construction.

## Files
- `families.py`: the clause/provision topics (ceilings, floors, agreed-otherwise rules, mandatory forms, bans, vague
  clauses) and the sample maker. `HOLDOUT` topics only appear in the evaluation set.
- `build.py`: writes `data/train.jsonl`, `data/valid.jsonl`, `data/eval.jsonl`. Briefs and schemas come from
  `NewIdea.services.clause_risk_service`, so training matches inference; every target passes the service's own quote
  checks. `--real` adds samples on real provisions from the knowledge base (BLDS Điều 468, Luật Thương mại Điều 301)
  with their numbers moved.
- `evaluate.py`: runs the evaluation set through `review_clause` against the served model and reports conflict recall,
  false legal risks, vague clauses reported as suggestions, changed-law twins answered right, and the holdout topics.

## Steps
```
docker exec riskdl_web python -m training.risk_skill.build --train 2400 --real
docker exec riskdl_web python -m training.risk_skill.evaluate --label qwen3-8b-base
# train a LoRA on data/train.jsonl (Kaggle notebook), serve it, then:
docker exec riskdl_web python -m training.risk_skill.evaluate --label qwen3-8b-lora
```
A record: `messages` (system + user brief), `schema` (the JSON schema the server enforces), `target` (the answer to
learn), `expect` (what the evaluation checks).
