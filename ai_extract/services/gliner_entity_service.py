"""Independent source-region entity and allowlisted relation proposals."""
import gc
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
from ai_extract import STRUCTURE_REVIEW_SCHEMA

MODEL_ID='knowledgator/gliner-relex-multi-v1.0'
ENTITY_SCHEMA='gliner-entities-v3-context'
CONTEXT_SEPARATOR='\n\n[Source boundary]\n\n'
ENTITY_LABELS={
    'organization':'ORGANIZATION', 'person':'PERSON', 'contract number':'CONTRACT_NUMBER',
    'tax identification number':'TAX_CODE', 'money amount':'MONEY_AMOUNT', 'currency':'CURRENCY',
    'date':'DATE', 'duration':'DURATION', 'percentage':'PERCENTAGE', 'product':'PRODUCT',
    'service':'SERVICE', 'location':'LOCATION', 'bank account':'BANK_ACCOUNT', 'legal reference':'LEGAL_REFERENCE',
    'document section':'DOCUMENT_SECTION','defined term':'DEFINED_TERM',
    'obligation':'OBLIGATION','condition':'CONDITION','exception':'EXCEPTION',
}

_runtime=None
RELATION_LABELS={'references':'references','defines':'defines','obligates':'obligates',
    'requires':'depends_on','part of':'part_of','describes':'describes','applies to':'applies_to',
    'has amount':'has_amount','has deadline':'has_deadline','pays to':'pays_to'}


def valid_score(value, threshold):
    return (isinstance(value,(int,float)) and not isinstance(value,bool)
            and math.isfinite(value) and threshold<=value<=1)


def mention_key(item):
    return hashlib.sha256(json.dumps([item['source_id'],item['start'],item['end'],item['entity_type']],ensure_ascii=False).encode()).hexdigest()


def unload():
    global _runtime
    if _runtime is None:return dict(model=MODEL_ID,loaded=False)
    _runtime=None;gc.collect()
    import torch
    if torch.cuda.is_available():torch.cuda.empty_cache()
    return dict(model=MODEL_ID,loaded=False)


def runtime():
    global _runtime
    if _runtime is None:
        import torch
        from gliner import GLiNER
        if not torch.cuda.is_available():raise RuntimeError('GLiNER requires configured CUDA GPU')
        path=Path(os.getenv('GLINER_MODEL_PATH','scratch/a3-models/gliner-relex-multi-v1.0'))
        if not (path/'gliner_config.json').is_file() or not (path/'model.safetensors').is_file():
            raise RuntimeError('GLiNER checkpoint not installed')
        _runtime=GLiNER.from_pretrained(str(path),
            cache_dir=os.getenv('GLINER_ENCODER_CACHE','scratch/a3-models/gliner-encoder-cache'),
            local_files_only=True,map_location='cuda',strict=True,
            dtype=torch.float16,low_cpu_mem_usage=True).eval()
        print(json.dumps(dict(event='gliner_load',model=MODEL_ID,device='cuda',task='entity_relation_proposals')),flush=True)
    return _runtime


def text_windows(text, words_per_window=160, overlap=24):
    """Keep exact character offsets; overlap protects entities at window boundaries."""
    if not 0<=overlap<words_per_window:raise ValueError('Invalid entity window overlap')
    tokens=list(re.finditer(r'\S+',text))
    start=0
    while start<len(tokens):
        stop=min(len(tokens),start+words_per_window)
        a,b=tokens[start].start(),tokens[stop-1].end()
        yield a,text[a:b]
        if stop==len(tokens):break
        start=stop-overlap


def validate_mentions(text,mentions,threshold=.65):
    """A label/score never substitutes for an exact source span."""
    accepted=[]
    for mention in mentions:
        start,end=mention.get('start'),mention.get('end')
        label=mention.get('label');score=mention.get('score')
        if (not isinstance(start,int) or isinstance(start,bool) or not isinstance(end,int) or isinstance(end,bool)
            or not 0<=start<end<=len(text) or label not in ENTITY_LABELS
            or not valid_score(score,threshold)
            or mention.get('text')!=text[start:end] or not text[start:end].strip()):
            continue
        accepted.append(dict(start=start,end=end,text=text[start:end],entity_type=ENTITY_LABELS[label],score=float(score)))
    return accepted


def infer_entities(units,predictor=None):
    started=time.perf_counter();threshold=float(os.getenv('GLINER_ENTITY_THRESHOLD','.5'))
    relation_threshold=float(os.getenv('GLINER_RELATION_THRESHOLD','.8'))
    if not 0<=threshold<=1 or not 0<=relation_threshold<=1:raise ValueError('Invalid extraction threshold')
    pending=[]
    for unit in units:
        if 'context_windows' in unit:
            for window in unit['context_windows']:
                start,text=window['offset'],window['text']
                if unit['text'][start:start+len(text)]!=text:raise ValueError('Invalid target context offset')
                for context in window['contexts']:
                    if context['id']==unit['id'] or not context['text']:continue
                    boundary=len(text)+len(CONTEXT_SEPARATOR)
                    combined=text+CONTEXT_SEPARATOR+context['text']
                    spans=[(0,len(text),unit['id'],start),
                           (boundary,len(combined),context['id'],context['offset'])]
                    pending.append((unit['id'],combined,spans))
        else:
            for offset,text in text_windows(unit['text']):
                pending.append((unit['id'],text,[(0,len(text),unit['id'],offset)]))
    entities={};relations={}
    if pending:
        network=predictor or runtime()
        for index in range(0,len(pending),8):
            batch=pending[index:index+8]
            predictions,links=network.inference(texts=[r[1] for r in batch],labels=list(ENTITY_LABELS),
                relations=list(RELATION_LABELS),threshold=threshold,adjacency_threshold=.6,
                relation_threshold=relation_threshold,return_relations=True,batch_size=2)
            if len(predictions)!=len(batch) or len(links)!=len(batch):raise ValueError('GLiNER batch source coverage mismatch')
            for (target,text,spans),mentions,proposals in zip(batch,predictions,links):
                local={}
                for mention in validate_mentions(text,mentions,threshold):
                    span=next((s for s in spans if s[0]<=mention['start']<mention['end']<=s[1]),None)
                    if span is None:continue
                    low,high,source,offset=span
                    start,end=offset+mention['start']-low,offset+mention['end']-low
                    key=(source,start,end,mention['entity_type'])
                    entity=dict(source_id=source,start=start,end=end,name=mention['text'],
                                entity_type=mention['entity_type'],confidence=mention['score'],
                                origin='gliner_source_span',review_status='unreviewed')
                    if key not in entities or entity['confidence']>entities[key]['confidence']:entities[key]=entity
                    local[(mention['start'],mention['end'],mention['entity_type'])]=entity
                for link in proposals:
                    score=link.get('score');label=link.get('relation')
                    if label not in RELATION_LABELS or not valid_score(score,relation_threshold):continue
                    endpoints=[]
                    for side in ('head','tail'):
                        endpoint=link.get(side,{})
                        if not isinstance(endpoint,dict):continue
                        if any(not isinstance(endpoint.get(k),int) or isinstance(endpoint[k],bool) for k in ('start','end')):continue
                        item=local.get((endpoint.get('start'),endpoint.get('end'),ENTITY_LABELS.get(endpoint.get('type'))))
                        if item and endpoint.get('text')==item['name']:endpoints.append(item)
                    if len(endpoints)!=2:continue
                    a,b=[mention_key(item) for item in endpoints]
                    if a==b:continue
                    source=endpoints[0]['source_id'];destination=endpoints[1]['source_id']
                    own=next(s for s in spans if s[2]==source)
                    other=next(s for s in spans if s[2]==destination)
                    key=(source,a,b,RELATION_LABELS[label])
                    if key not in relations or score>relations[key]['confidence']:
                        relations[key]=dict(source_id=source,from_key=a,to_key=b,predicate=RELATION_LABELS[label],
                            quote=text[own[0]:own[1]],target_source_id=destination,
                            target_quote=text[other[0]:other[1]],confidence=float(score),
                            origin='gliner_relex_source_span',review_status='unreviewed')
            print(json.dumps(dict(event='gliner_batch',windows_completed=min(index+8,len(pending)),windows_total=len(pending),
                                  entities=len(entities),relations=len(relations))),flush=True)
    metrics=dict(windows=len(pending),sources=len(units),entities=len(entities),relations=len(relations),
                             elapsed_s=round(time.perf_counter()-started,3),threshold=threshold,
                             device=str(getattr(predictor or _runtime,'device','cuda')) if pending else None)
    if predictor is None and pending:
        import torch
        metrics.update(cuda_allocated_gb=round(torch.cuda.memory_allocated()/1e9,3),
                       cuda_peak_allocated_gb=round(torch.cuda.max_memory_allocated()/1e9,3))
    return dict(model=MODEL_ID,provider='gliner',entity_schema=ENTITY_SCHEMA,entities=list(entities.values()),
                relations=list(relations.values()),metrics=metrics)


def _request_runtime(route,payload,timeout=600):
    import requests
    from django.conf import settings
    from .contract_pipeline_service import NGROK_HEADERS
    response=requests.post(settings.RAG_INFERENCE_URL.rstrip('/')+'/rag/'+route,
                           json=payload,headers=NGROK_HEADERS,timeout=timeout)
    response.raise_for_status();result=response.json()
    if result.get('model')!=MODEL_ID:raise ValueError('Invalid GLiNER runtime model')
    return result


def request_entities(units):
    result=_request_runtime('gliner_entities',dict(units=units),timeout=(5,None))
    if result.get('model')!=MODEL_ID or result.get('provider')!='gliner':raise ValueError('Invalid GLiNER provider')
    if result.get('entity_schema')!=ENTITY_SCHEMA:
        raise ValueError('GLiNER runtime is outdated; restart A3 to load the entity schema')
    return result


def infer_identity_pairs(pairs, predictor=None):
    """Ask the existing multilingual RelEx model about bounded source pairs.

    Both endpoints must be literal names inside their own supplied source.
    Similar names or embeddings alone never produce an identity decision.
    """
    if (not isinstance(pairs,list) or len(pairs)>16 or any(
            not isinstance(p,dict) or not isinstance(p.get('id'),str)
            or not isinstance(p.get('left'),dict) or not isinstance(p.get('right'),dict) for p in pairs)
            or len({p['id'] for p in pairs})!=len(pairs)):
        raise ValueError('Invalid identity batch')
    texts, ranges, input_spans = [], [], []
    for pair in pairs:
        left,right=pair['left'],pair['right']
        if any(not isinstance(v.get('name'),str) or not v['name'] or not isinstance(v.get('context'),str)
               or v['name'] not in v['context'] or len(v['context'])>2500 for v in (left,right)):
            raise ValueError('Identity endpoints require their source quotations')
        text=left['context']+CONTEXT_SEPARATOR+right['context']
        texts.append(text);ranges.append((len(left['context']),len(left['context'])+len(CONTEXT_SEPARATOR)))
        a=left['context'].index(left['name'])
        b=len(left['context'])+len(CONTEXT_SEPARATOR)+right['context'].index(right['name'])
        input_spans.append([dict(start=a,end=a+len(left['name'])),dict(start=b,end=b+len(right['name']))])
    if not texts:return dict(model=MODEL_ID,decisions=[])
    _,proposals=(predictor or runtime()).inference(texts=texts,labels=list(ENTITY_LABELS),
        relations=['same entity as','different entity from'],threshold=.5,adjacency_threshold=0.,
        input_spans=input_spans,relation_threshold=0.,return_relations=True,batch_size=2)
    if len(proposals)!=len(pairs):raise ValueError('Incomplete identity pair inference')
    decisions=[]
    for pair,text,links,(end,start) in zip(pairs,texts,proposals,ranges):
        scores={'same entity as':0.,'different entity from':0.}
        for link in links:
            if link.get('relation') not in scores or not valid_score(link.get('score'),.5):continue
            endpoints=[link.get('head',{}),link.get('tail',{})]
            def grounded(endpoint,side):
                low,high=(0,end) if side=='left' else (start,len(text))
                a,b=endpoint.get('start'),endpoint.get('end')
                return (type(a) is int and type(b) is int and low<=a<b<=high
                    and endpoint.get('text')==pair[side]['name']
                    and text[a:b]==pair[side]['name'])
            if not ((grounded(endpoints[0],'left') and grounded(endpoints[1],'right'))
                    or (grounded(endpoints[1],'left') and grounded(endpoints[0],'right'))):continue
            scores[link['relation']]=max(scores[link['relation']],float(link['score']))
        same,different=scores.values()
        decisions.append(dict(id=pair['id'],same=same,different=different,
            status='same' if same>=.9 and same-different>=.1 else 'different' if different>=.9 and different-same>=.1 else 'unresolved'))
    return dict(model=MODEL_ID,decisions=decisions,policy='model_inference_not_verified_identity')


def request_identity_pairs(pairs):
    result=_request_runtime('gliner_identity',dict(pairs=pairs))
    if len(result['decisions'])!=len(pairs) or {r['id'] for r in result['decisions']}!={p['id'] for p in pairs}:
        raise ValueError('Invalid identity runtime response')
    return result


def infer_structure_pairs(pairs,predictor=None):
    """Review region order/containment without inventing a layout from NER."""
    if (not isinstance(pairs,list) or len(pairs)>16 or any(not isinstance(p,dict)
            or not isinstance(p.get('id'),str) or p.get('kind') not in {'NEXT','CONTAINS'}
            or any(not isinstance(p.get(side),str) or not p[side].strip() or len(p[side])>1800
                   for side in ('left','right')) for p in pairs)
            or len({p['id'] for p in pairs})!=len(pairs)):
        raise ValueError('Invalid structure review batch')
    if not pairs:return dict(model=MODEL_ID,schema=STRUCTURE_REVIEW_SCHEMA,decisions=[])
    labels={'reading follows':('NEXT',-1),'reading precedes':('NEXT',1),
            'section contains content':('CONTAINS',1),'content belongs to section':('CONTAINS',-1)}
    texts=[p['left']+CONTEXT_SEPARATOR+p['right'] for p in pairs]
    _,outputs=(predictor or runtime()).inference(texts=texts,labels=[*ENTITY_LABELS,'document heading','document paragraph'],
        relations=list(labels),threshold=.5,adjacency_threshold=.5,relation_threshold=.5,
        return_relations=True,batch_size=2)
    if len(outputs)!=len(pairs):raise ValueError('Incomplete structure review')
    decisions=[]
    for pair,text,links in zip(pairs,texts,outputs):
        supported=reverse=0.;evidence=[]
        boundary=len(pair['left']);right_start=boundary+len(CONTEXT_SEPARATOR)
        def side(endpoint):
            start,end=endpoint.get('start'),endpoint.get('end')
            if (type(start) is not int or type(end) is not int or not 0<=start<end<=len(text)
                    or endpoint.get('text')!=text[start:end]):return 0
            return 1 if end<=boundary else -1 if start>=right_start else 0
        for link in links:
            relation=labels.get(link.get('relation'))
            if not relation or relation[0]!=pair['kind'] or not valid_score(link.get('score'),.9):continue
            head,tail=link.get('head',{}),link.get('tail',{})
            direction=side(head)
            if not direction or side(tail)!=-direction:continue
            agrees=direction*relation[1]==1
            if agrees:supported=max(supported,float(link['score']))
            else:reverse=max(reverse,float(link['score']))
            evidence.append(dict(predicate=link['relation'],head=head['text'],tail=tail['text'],confidence=float(link['score'])))
        status='supported' if supported>=.9 and supported-reverse>=.1 else 'disputed' if reverse>=.9 and reverse-supported>=.1 else 'unresolved'
        decisions.append(dict(id=pair['id'],status=status,supported=supported,reverse=reverse,evidence=evidence))
    return dict(model=MODEL_ID,schema=STRUCTURE_REVIEW_SCHEMA,decisions=decisions,policy='model_proposal_not_verified_structure')


def request_structure_pairs(pairs):
    result=_request_runtime('gliner_structure',dict(pairs=pairs))
    if (result.get('schema')!=STRUCTURE_REVIEW_SCHEMA or len(result['decisions'])!=len(pairs)
            or {r['id'] for r in result['decisions']}!={p['id'] for p in pairs}):
        raise ValueError('Invalid structure review response')
    return result


def document_context_units(tree,embedding=None):
    """Retrieve candidate windows; retrieval scores never create graph relations."""
    import numpy as np
    from shared.retrieval import lexical_search
    from .contract_pipeline_service import HybridBackend
    leaves=[l for l in tree['leaves'] if l.get('text','').strip()
        and l.get('layout_type') not in {'page_header','page_footer'}
        and l.get('structure_metadata',{}).get('ocr_status') not in {'failed','rejected','empty','unresolved'}
        and l.get('structure_metadata',{}).get('visual_ocr_status')!='failed']
    windows=[];by_source={};by_node={}
    for leaf in leaves:
        by_node.setdefault(leaf.get('node_id'),[]).append(leaf)
        for offset,text in text_windows(leaf['text'],64,16):
            item=dict(chunk_id=str(len(windows)),id=leaf['chunk_id'],offset=offset,text=text)
            windows.append(item);by_source.setdefault(leaf['chunk_id'],[]).append(item)
    dense=None;error=None
    if len(by_source)>1:
        try:
            unique=list(dict.fromkeys(w['text'] for w in windows))
            vectors=(embedding or HybridBackend().embedding)(unique)
            lookup=dict(zip(unique,vectors))
            dense=np.asarray([lookup[w['text']] for w in windows],dtype=np.float32)
            norms=np.linalg.norm(dense,axis=1,keepdims=True)
            if dense.ndim!=2 or len(vectors)!=len(unique) or not np.isfinite(dense).all() or (norms==0).any():
                raise ValueError('Invalid document candidate embeddings')
            dense=dense/norms
        except Exception as exc:dense=None;error=type(exc).__name__
    adjacent={}
    for stream in tree.get('reading_streams',[]):
        if stream['status']=='unresolved':continue
        ids=[i for item in stream['items'] for i in item['leaf_ids'] if i in by_source]
        for index,identity in enumerate(ids):
            adjacent[identity]=[(ids[index-1],-1)] if index else []
            if index+1<len(ids):adjacent[identity].append((ids[index+1],0))
    limit=max(1,int(os.getenv('GLINER_DOCUMENT_CANDIDATES','2')))
    units={l['chunk_id']:dict(id=l['chunk_id'],text=l['text'],context_windows=[]) for l in leaves}
    leaf_map={l['chunk_id']:l for l in leaves};pair_count=0
    for index,window in enumerate(windows):
        identity=window['id'];local=[]
        for source,position in adjacent.get(identity,[]):local.append(by_source[source][position])
        for heading in by_node.get(leaf_map[identity].get('node_id'),[]):
            if heading.get('layout_type')=='title' and heading['chunk_id']!=identity:
                local.append(by_source[heading['chunk_id']][0])
        candidates=[w for w in windows if w['id']!=identity]
        ranks=[lexical_search(window['text'],candidates,limit=limit)]
        if dense is not None:
            scores=dense@dense[index]
            ranks.append(sorted(candidates,key=lambda w:float(scores[int(w['chunk_id'])]),reverse=True)[:limit])
        fused={}
        for rows in ranks:
            for rank,item in enumerate(rows):
                fused[item['chunk_id']]=fused.get(item['chunk_id'],0)+1/(60+rank)
        selected=local+[windows[int(i)] for i in sorted(fused,key=fused.get,reverse=True)[:limit]]
        contexts=list({w['chunk_id']:dict(id=w['id'],offset=w['offset'],text=w['text']) for w in selected}.values())
        if contexts:
            units[identity]['context_windows'].append(dict(offset=window['offset'],text=window['text'],contexts=contexts))
            pair_count+=len(contexts)
    return [u for u in units.values() if u['context_windows']],dict(
        state='dense_and_lexical' if dense is not None else 'lexical_only' if error else 'empty' if len(by_source)<2 else 'lexical',
        dense_error=error,source_count=len(leaves),windows=len(windows),candidate_pairs=pair_count,
        semantics='candidates_only_not_relationships')


def enrich_document_relations(tree,knowledge,request_model=None,embedding=None):
    """One whole-document context pass after OCR, including cross-page candidates."""
    units,search=document_context_units(tree,embedding)
    result=extract_graph_entities(tree,request_model,context_units=units)
    entities={e['key']:e for e in knowledge.get('entities',[])}
    entities.update({e['key']:e for e in result['entities']})
    relations={(r['from_key'],r['to_key'],r['predicate']):r for r in knowledge.get('relations',[])}
    relations.update({(r['from_key'],r['to_key'],r['predicate']):r for r in result['relations']})
    links={(r['from_id'],r['to_id'],r['kind'],r.get('from_key'),r.get('to_key')):r
           for r in knowledge.get('source_relations',[])+result['source_relations']}
    status=knowledge.get('status','complete')
    if result['status'] in {'partial','unavailable'} and status in {'complete','empty'}:status='partial'
    return dict(knowledge,status=status,entities=list(entities.values()),relations=list(relations.values()),source_relations=list(links.values()),
        document_relations=dict(status=result['status'],candidate_search=search,errors=result['errors'],metrics=result['metrics']),
        cross_page_semantics='gliner_context_proposals_not_verified',
        validation_scope='source_spans_on_both_sides_not_semantic_truth')


def extract_graph_entities(tree,request_model=None,context_units=None):
    readable=[l for l in tree['leaves'] if l.get('text','').strip()]
    excluded={l['chunk_id'] for l in readable if
        l.get('structure_metadata',{}).get('ocr_status') in {'failed','rejected','empty','unresolved'}
        or l.get('structure_metadata',{}).get('visual_ocr_status')=='failed'}
    originals={l['chunk_id']:l['text'] for l in readable if l['chunk_id'] not in excluded}
    units=context_units if context_units is not None else [dict(id=i,text=text) for i,text in originals.items()]
    entities={};relations={};errors=[];metrics=[];completed=[]
    for index in range(0,len(units),16):
        batch=units[index:index+16];sources={u['id']:u['text'] for u in batch};pairs=[]
        for unit in batch:
            for window in unit.get('context_windows',[]):
                if originals.get(unit['id'],'')[window['offset']:window['offset']+len(window['text'])]!=window['text']:
                    raise ValueError('Target context does not match source')
                for context in window['contexts']:
                    text=originals.get(context['id'],'')
                    if text[context['offset']:context['offset']+len(context['text'])]!=context['text']:
                        raise ValueError('Context does not match source')
                    sources[context['id']]=text
                    pairs.append((unit['id'],window['offset'],window['offset']+len(window['text']),
                                  context['id'],context['offset'],context['offset']+len(context['text'])))
        try:
            result=(request_model or request_entities)(batch)
            for item in result.get('entities',[]):
                source=item.get('source_id');start,end=item.get('start'),item.get('end')
                if (source not in sources or not isinstance(start,int) or isinstance(start,bool) or not isinstance(end,int) or isinstance(end,bool)
                    or not 0<=start<end<=len(sources[source]) or item.get('name')!=sources[source][start:end]
                    or item.get('entity_type') not in ENTITY_LABELS.values()
                    or not valid_score(item.get('confidence'),float(os.getenv('GLINER_ENTITY_THRESHOLD','.5')))):
                    raise ValueError('Ungrounded entity mention')
                if pairs and not any((source==a and lo<=start<end<=hi) or (source==b and low<=start<end<=high)
                                     for a,lo,hi,b,low,high in pairs):
                    raise ValueError('Entity lies outside supplied context windows')
            local={mention_key(item):item for item in result.get('entities',[])}
            for link in result.get('relations',[]):
                source=link.get('source_id');a=local.get(link.get('from_key'));b=local.get(link.get('to_key'))
                cross=a and b and a['source_id']!=b['source_id']
                permitted=not cross or any(
                    x==a['source_id'] and y==b['source_id'] and lo<=a['start']<a['end']<=hi and low<=b['start']<b['end']<=high
                    for x,lo,hi,y,low,high in pairs+[(y,lo2,hi2,x,lo1,hi1) for x,lo1,hi1,y,lo2,hi2 in pairs])
                if (not a or not b or not permitted or link['from_key']==link['to_key'] or a['source_id']!=source
                    or link.get('target_source_id',source)!=b['source_id']
                    or link.get('predicate') not in RELATION_LABELS.values() or source not in sources
                    or not isinstance(link.get('quote'),str) or not link['quote'] or link['quote'] not in sources[source]
                    or not valid_score(link.get('confidence'),float(os.getenv('GLINER_RELATION_THRESHOLD','.8')))):
                    raise ValueError('Ungrounded or cross-region relation')
                if cross and (link.get('target_source_id')!=b['source_id'] or not link.get('target_quote')
                              or link['target_quote'] not in sources[b['source_id']]
                              or a['name'] not in link['quote'] or b['name'] not in link['target_quote']):
                    raise ValueError('Cross-region relation requires both source quotations')
            # Validate the whole batch before accepting any proposal.
            for item in result.get('entities',[]):
                key=mention_key(item)
                entities[key]=dict(item,key=key,source_ids=[item['source_id']],origin='gliner_source_span',review_status='unreviewed')
            for link in result.get('relations',[]):
                key=(link['source_id'],link['from_key'],link['to_key'],link['predicate'])
                relations[key]=dict(link,scope_quote=sources[link['source_id']],origin='gliner_relex_source_span',
                    review_status='unreviewed',qualification_validation='source_spans_not_semantic_truth')
            metrics.append(result.get('metrics',{}))
            completed.extend(u['id'] for u in batch)
        except Exception as error:
            errors.append(dict(source_ids=list(sources),error_type=type(error).__name__,reason=str(error)[:200]))
            # An unavailable runtime must not cause dozens of identical failing calls.
            if index==0 and not entities:break
    mentioned={e['source_id'] for e in entities.values()}
    coverage=dict(eligible_ids=[u['id'] for u in units],completed_ids=completed,
                  without_entity_ids=[i for i in completed if i not in mentioned],excluded_ocr_ids=sorted(excluded))
    print(json.dumps(dict(event='gliner_coverage',eligible=len(units),completed=len(completed),without_entity=len(coverage['without_entity_ids']),excluded_ocr=len(excluded))),flush=True)
    links=[]
    for link in relations.values():
        target=link.get('target_source_id',link['source_id'])
        if link['predicate']=='references' and target!=link['source_id']:
            links.append(dict(from_id=link['source_id'],to_id=target,kind='references',from_quote=link['quote'],
                to_quote=link['target_quote'],from_key=link['from_key'],to_key=link['to_key'],confidence=link['confidence'],
                origin='gliner_relex_source_span',review_status='unreviewed'))
    return dict(model=MODEL_ID,provider='gliner',status='partial' if errors and completed else 'unavailable' if errors else 'complete' if units else 'empty',
                entities=list(entities.values()),relations=list(relations.values()),source_relations=links,errors=errors,metrics=metrics,
                source_count=len(units),source_coverage=coverage,validation_scope='source_region_spans_and_allowlist_not_semantic_accuracy')
