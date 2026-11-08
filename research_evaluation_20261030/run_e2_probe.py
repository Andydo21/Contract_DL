"""E2 one-question exploratory probe over frozen, actual Neo4j graphs.

No automatic quality labels. Token ceiling is checked against API usage after
generation because this gateway does not expose a tokenizer endpoint.
"""
import csv
import hashlib
import json
import random
import statistics
import time
from collections import defaultdict
from pathlib import Path

from evaluation.ablation_adapters import messages
from evaluation.io import digest
from evaluation.metrics import evidence_metrics
from evaluation.runners.common import Gateway, check_response

ROOT = Path('/app')
BASE = ROOT / 'research_evaluation_20261030'
OUT = BASE / 'E2_probe'
seed_data = json.loads((OUT / 'retrieval_seed.json').read_text(encoding='utf8'))
graphs = json.loads((OUT / 'graph_snapshots.json').read_text(encoding='utf8'))
question = json.loads((BASE / 'pilot50_current_questions.jsonl').read_text(encoding='utf8').splitlines()[0])
config = json.loads((ROOT / 'evaluation/config.json').read_text(encoding='utf8'))
gateway = Gateway(config['generator'])
models = gateway.health()

sources, keys, adjacency = {}, {}, defaultdict(list)
for graph in graphs:
    version, scope = graph['version_id'], graph['scope']['key']
    for leaf in graph['leaves']:
        identity = f"a3:v{version}:r{graph['run_id']}:{leaf['chunk_id']}"
        sources[identity] = dict(evidence_id=identity, text=leaf.get('text',''),
            document_id=leaf['document_id'], version=version, page=leaf['page_number'],
            region=leaf.get('bbox'), breadcrumb=leaf.get('heading_path',[]),
            scope=dict(document_id=leaf['document_id'],version_id=version,
                       heading_path=leaf.get('heading_path',[])),links=[],
            layout_type=leaf.get('layout_type'),chunk_id=leaf['chunk_id'])
        keys[scope+':leaf:'+leaf['chunk_id']] = identity
    for node in graph['nodes']:
        keys.setdefault(node['key'], node)
    for edge in graph['edges']:
        adjacency[edge['source']].append((edge['target'], edge, 'forward'))
        adjacency[edge['target']].append((edge['source'], edge, 'reverse'))

seeds = []
for item in seed_data['seeds']:
    graph = next(g for g in graphs if g['version_id'] == item['version_id'])
    key = graph['scope']['key']+':leaf:'+item['chunk_id']
    seeds.append(keys[key])
if len(seeds) != len(set(seeds)):
    raise ValueError('Duplicate seed IDs')

def owners(evidence_key):
    return [(target, edge) for target,edge,direction in adjacency[evidence_key]
            if edge['type']=='HAS_EVIDENCE' and direction=='reverse']

def neighbors(mode):
    selected = list(seeds)
    trace = []
    started = time.perf_counter()
    if mode == 'A':
        return selected, trace, (time.perf_counter()-started)*1000
    key_by_id = {value:key for key,value in keys.items() if isinstance(value,str)}
    for seed in seeds:
        for owner, binding in owners(key_by_id[seed]):
            for target, relation, direction in adjacency[owner]:
                allowed = relation['type']=='NEXT' if mode=='B' else relation['type'] in {'NEXT','CONTAINS'}
                if not allowed:
                    continue
                target_node=keys.get(target)
                if not isinstance(target_node,dict):
                    continue
                if relation['type']=='CONTAINS' and target_node.get('kind')=='document':
                    trace.append(dict(seed=seed,path=[binding,relation],accepted=False,reason='document_root'))
                    continue
                for leaf_key, edge, edge_dir in adjacency[target]:
                    if edge['type']!='HAS_EVIDENCE' or edge_dir!='forward' or leaf_key not in keys:
                        continue
                    identity=keys[leaf_key]
                    if not isinstance(identity,str) or identity not in sources:
                        continue
                    left,right=sources[seed],sources[identity]
                    reason = None
                    if left['document_id']!=right['document_id'] or left['version']!=right['version']:
                        reason='document_version_boundary'
                    elif not right['text'].strip():
                        reason='no_text_for_text_probe'
                    elif identity in selected:
                        reason='already_selected'
                    elif mode=='D' and left['breadcrumb']!=right['breadcrumb']:
                        reason='heading_scope_boundary'
                    trace.append(dict(seed=seed,target=identity,path=[binding,relation,edge],
                                      accepted=reason is None,reason=reason or 'admitted'))
                    if reason is None:
                        selected.append(identity)
    return selected,trace,(time.perf_counter()-started)*1000

variants={mode:neighbors(mode) for mode in 'ABCD'}
schedule=[(mode,rep) for mode in 'ABCD' for rep in range(3)]
random.Random(1729).shuffle(schedule)
manifest=dict(experiment='E2_exploratory_probe',question_id=question['question_id'],
    gold_approved=False, independent_test=False,seed_evidence_ids=seeds,
    seed_retrieval_sha256=hashlib.sha256((OUT/'retrieval_seed.json').read_bytes()).hexdigest(),
    graph_sha256=hashlib.sha256((OUT/'graph_snapshots.json').read_bytes()).hexdigest(),
    modes={'A':'none','B':'NEXT edges in either direction','C':'B plus direct CONTAINS',
           'D':'C with identical heading paths'},model=models,generator=config['generator'],
    renderer='canonical', max_input_tokens=config['experiment']['max_input_tokens'],
    tokenizer_preflight='unavailable; budget checked post-generation using API usage',
    graph_latency_scope='in-memory traversal only; excludes snapshot fetch',schedule=schedule)
(OUT/'probe_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,default=str),encoding='utf8')
for mode, rep in schedule:
    ids,trace,graph_ms=variants[mode]
    selected=[sources[identity] for identity in ids]
    chat=messages(question['question'],selected,'E')
    body=gateway.request_body(chat,config['generator']['seed']+rep)
    body['response_format']={'type':'json_schema','json_schema':{'name':'e2_probe','strict':True,
      'schema':{'type':'object','additionalProperties':False,'required':['answer','claims'],
      'properties':{'answer':{'type':'string'},'claims':{'type':'array','items':{'type':'object',
      'additionalProperties':False,'required':['subject','attribute','value','condition','evidence_ids'],
      'properties':{'subject':{'type':'string'},'attribute':{'type':'string'},'value':{'type':'string'},
      'condition':{'type':'string'},'evidence_ids':{'type':'array','items':{'type':'string','enum':ids}}}}}}}}}
    row=dict(experiment='E2_exploratory_probe',question_id=question['question_id'],variant=mode,
        repetition=rep,seed_evidence_ids=seeds,selected_evidence_ids=ids,graph_trace=trace,
        graph_latency_ms=graph_ms,prompt=chat,request=body,accuracy=None,attribute_leakage_rate=None,
        gold_status='unreviewed',citation_faithfulness=None)
    row['provisional_evidence_metrics']=evidence_metrics(ids,question['gold_evidence_ids'],
        question['required_evidence_ids'],config['experiment']['top_k'])
    started=time.perf_counter()
    try:
        response,latency=gateway.generate(body)
        row['generation_http_ms']=latency
        check_response(row,response,config['generator']['model'],None)
        row['input_budget_valid']=row['input_tokens']<=config['experiment']['max_input_tokens']
        row['status']='completed_pending_review' if row['input_budget_valid'] else 'input_budget_exceeded'
    except Exception as error:
        row.update(status='failed',error_type=type(error).__name__,error=str(error)[:300])
        response=getattr(error,'response',None)
        if response is not None:row['provider_http_status']=response.status_code
    row['e2e_ms']=(time.perf_counter()-started)*1000+graph_ms
    with (OUT/'probe_runs.jsonl').open('a',encoding='utf8') as stream:
        stream.write(json.dumps(row,ensure_ascii=False,default=str)+'\n')
    print(mode,rep,row['status'],flush=True)
    if row.get('provider_http_status')==404:
        break
