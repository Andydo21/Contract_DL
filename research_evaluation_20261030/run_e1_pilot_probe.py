"""Run a single-question E1 probe; unreviewed pilot, not official results."""
import json
import os
import random
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from ai_extract.models import RetrievalSnapshot
from evaluation.ablation_adapters import messages
from evaluation.io import digest
from evaluation.runners.common import Gateway, check_response
from NewIdea.services.knowledge_answer_service import bind_graph_context

root = Path('/app')
base = root / 'research_evaluation_20261030'
out = base / 'E1_pilot_probe_02'
out.mkdir(exist_ok=True)
question = json.loads((base / 'pilot50_draft.jsonl').read_text(encoding='utf8').splitlines()[0])
mapping = {x['old_evidence_id']: x for x in
           (json.loads(line) for line in (base / 'pilot50_current_rebind.jsonl').read_text(encoding='utf8').splitlines())}
contexts = {x['version_id']: x['context'] for x in
            json.loads((base / 'pilot50_current_graph_contexts.json').read_text(encoding='utf8'))}
evidence, production_sources = [], []
for eid in question['gold_evidence_ids']:
    binding = mapping[eid]
    snapshot = RetrievalSnapshot.objects.get(version_id=binding['version_id'])
    leaf = next(item for item in snapshot.tree['leaves'] if item['chunk_id'] == binding['chunk_id'])
    source = dict(leaf, evidence_id=eid)
    production_sources.append(source)
    evidence.append(dict(evidence_id=eid, text=source['text'], document_id=source['document_id'],
        version=source['version_id'], page=source['page_number'], region=source['bbox'],
        breadcrumb=source.get('heading_path', []), scope=dict(document_id=source['document_id'],
        version_id=source['version_id'], heading_path=source.get('heading_path', [])),
        links=[], production_source=source))
versions = {source['version_id'] for source in production_sources}
graph = bind_graph_context([contexts[version] for version in sorted(versions)], production_sources,
                           query=question['question'])
config = json.loads((root / 'evaluation/config.json').read_text(encoding='utf8'))
gateway = Gateway(config['generator'])
models = gateway.health()
schedule = [(variant, rep) for variant in 'ABCDE' for rep in range(3)]
random.Random(1729).shuffle(schedule)
manifest = dict(experiment='E1_exploratory_probe', question_id=question['question_id'],
    review_status=question['review_status'], gold_approved=False, independent_test=False,
    renderer='production E; canonical A-D', evidence_ids=question['gold_evidence_ids'],
    evidence_hash=digest(evidence), model=models, checkpoint_revision='unverified', gpu='unverified',
    tokenizer_preflight='unavailable; response usage recorded', retrieval='fixed provisional evidence only',
    generation=config['generator'], schedule=schedule, graph_nodes=len(graph['nodes']), graph_edges=len(graph['edges']))
(out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding='utf8')
for variant, rep in schedule:
    chat = messages(question['question'], evidence, variant, renderer='production', graph=graph)
    body = gateway.request_body(chat, config['generator']['seed'] + rep)
    ids = question['gold_evidence_ids']
    body['response_format'] = {'type':'json_schema','json_schema':{'name':'e1_probe','strict':True,
        'schema':{'type':'object','additionalProperties':False,'required':['answer','claims'],
        'properties':{'answer':{'type':'string'},'claims':{'type':'array','items':{'type':'object',
        'additionalProperties':False,'required':['subject','attribute','value','condition','evidence_ids'],
        'properties':{'subject':{'type':'string'},'attribute':{'type':'string'},'value':{'type':'string'},
        'condition':{'type':'string'},'evidence_ids':{'type':'array','items':{'type':'string','enum':ids}}}}}}}}}
    row = dict(experiment='E1_exploratory_probe', question_id=question['question_id'], variant=variant,
        repetition=rep, evidence_ids=ids, selected_evidence_ids=ids, evidence_hash=digest(evidence),
        prompt=chat, request=body, review_status='pending', accuracy=None,
        attribute_leakage_rate=None, citation_faithfulness=None)
    try:
        response, latency = gateway.generate(body)
        row['generation_http_ms'] = latency
        check_response(row, response, config['generator']['model'], None)
        row['status'] = 'completed_pending_review'
    except Exception as error:
        row.update(status='failed', error_type=type(error).__name__, error=str(error)[:300])
        response = getattr(error, 'response', None)
        if response is not None:
            row['provider_http_status'] = response.status_code
    with (out / 'questions.jsonl').open('a', encoding='utf8') as stream:
        stream.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')
    print(variant, rep, row['status'], flush=True)
    if row.get('provider_http_status') == 404:
        break
