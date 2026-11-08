"""GLiNER2 identity/topic/polarity classification and NLI source entailment.

This module does not write to the graph. Scores are uncalibrated model outputs;
passing the operational threshold is not a claim of measured accuracy.
"""
import math
import json
import unicodedata
import hashlib

# Multilingual GLiNER2 (mDeBERTa-v3). The English base (deberta-v3) read Vietnamese contexts poorly: it kept
# "Bộ Ngoại giao" apart from itself and flipped its verdict when the two passages swapped places.
MODEL_ID='fastino/gliner2-multi-v1'
REVISION='ce747d79a8e362d3dee0b0b26d1201f7f1a8615a'
MODEL_PATH='scratch/a3-models/gliner2-multi-v1'
SCHEMA='gliner2-context-merge-v5-calibrated-margins'
RELATION_REVIEW_SCHEMA='gliner2-nli-entity-relation-support-v3-direct'
NLI_MODEL_ID='cross-encoder/nli-deberta-v3-xsmall'
NLI_REVISION='a150876415327c80daeff35ca6f68f5ed8cf5c24'
NLI_SCHEMA='directed-source-entailment-v1'
NLI_LABELS=('contradiction','entailment','neutral')
PASSAGE_REVIEW_SCHEMA='gliner2-specific-passage-link-v1'
PASSAGE_LINK_LABELS={
    'specific_subject_link':'The passages concern the same identifiable subject, and provide a description, specification, condition, example, or complementary details about that subject.',
    'surface_overlap':'Only generic wording or similar words are shared. The passages do not identify the same specific subject.',
    'different_subjects':'The passages refer to different subjects or meanings, without a grounded topical connection.',
    'uncertain':'The fragments provide too little information to establish a specific subject connection.',
}
RELATION_KIND_LABELS={
    'direct_relation':'The source directly states a concrete functional, structural, spatial, or design relationship between the two entities themselves. The entities actually provide, use, include or interact with each other.',
    'information_about':'One entity supplies descriptions, videos, examples or other information about the other entity, rather than a concrete functional or structural relation between the entities themselves.',
    'co_occurrence':'The source only co-mentions the names or labels, without establishing a concrete relationship between the entities.',
    'uncertain':'The source is insufficient to decide what kind of connection the entities have.',
}


def direct_relation_supported(decision,claim=None):
    scores=decision.get('relation_kind_scores')
    if claim is not None and decision.get('relation_kind_digest')!=source_claim_digest(claim):return False
    return (isinstance(scores,list) and len(scores)==2 and all(isinstance(s,dict)
        and set(s)==set(RELATION_KIND_LABELS)
        and all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=1 for v in s.values())
        and s['direct_relation']>=.9
        and s['direct_relation']-max(v for k,v in s.items() if k!='direct_relation')>=.1 for s in scores))
RELATION_SUPPORT_LABELS={
    'affirmed':'The source explicitly affirms the proposed directed relationship as stated.',
    'negated':'The source explicitly denies or excludes the proposed relationship.',
    'conditional':'The relationship is only stated under a condition or exception, not as an unconditional fact.',
    'uncertain':'The source does not establish the relationship, including mere comparison, co-occurrence or different attribution.',
}


def relation_claim_verdict(scores):
    if (not isinstance(scores,list) or len(scores)!=2 or any(not isinstance(s,dict)
            or set(s)!=set(RELATION_SUPPORT_LABELS) or any(type(v) not in (int,float)
                or not math.isfinite(v) or not 0<=v<=1 for v in s.values()) for s in scores)):
        raise ValueError('Invalid entity relation support scores')
    winners=[max(s,key=s.get) for s in scores]
    if winners[0]!=winners[1]:return 'unresolved','presentation_disagreement'
    if winners[0]=='uncertain':return 'unresolved','model_uncertain'
    winner=winners[0]
    if all(s[winner]>=.9 and s[winner]-max(v for k,v in s.items() if k!=winner)>=.1 for s in scores):
        return winner,'consistent_source_support_classification'
    return 'unresolved','insufficient_source_support'


def source_claim_digest(claim):
    return hashlib.sha256(json.dumps([claim.get(k) for k in ('head','tail','predicate','source','target_source')],
        ensure_ascii=False).encode()).hexdigest()


def relation_hypotheses(claim,polarity):
    """Render the fixed ontology; a trained model decides source entailment."""
    a,b=claim['head'],claim['tail'];negative=polarity=='negated'
    forms={
        'part of':(f'{a} is {"not " if negative else ""}part of {b}.',f'{b} does not include {a} as a part.' if negative else f'{b} includes {a} as a part.'),
        'located in':(f'{a} is {"not " if negative else ""}located in {b}.',f'{a} is not situated in {b}.' if negative else f'{a} is situated in {b}.'),
        'designed by':(f'{a} was {"not " if negative else ""}designed by {b}.',f'{b} did not design {a}.' if negative else f'{b} designed {a}.'),
        'supports':(f'{a} does not support {b}.' if negative else f'{a} supports {b}.',f'{b} is {"not " if negative else ""}supported by {a}.'),
        'integrates with':(f'{a} does not integrate with {b}.' if negative else f'{a} integrates with {b}.',f'{a} does not have integration with {b}.' if negative else f'{a} has integration with {b}.'),
    }
    if claim['predicate'] not in forms:raise ValueError('Unsupported entailment predicate')
    return forms[claim['predicate']]


def source_entailment_supported(proof,polarity,claim=None):
    if not isinstance(proof,dict) or proof.get('schema')!=NLI_SCHEMA or proof.get('model')!=NLI_MODEL_ID or proof.get('revision')!=NLI_REVISION:
        return False
    if claim is not None and proof.get('claim_digest')!=source_claim_digest(claim):return False
    rows=proof.get(polarity)
    if not isinstance(rows,list) or len(rows)!=2:return False
    for row in rows:
        if (not isinstance(row,dict) or set(row)!=set(NLI_LABELS)
                or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in row.values())
                or abs(sum(row.values())-1)>.02):return False
        if row['entailment']<.9 or row['entailment']-max(row['contradiction'],row['neutral'])<.1:return False
    return True


def infer_source_entailment(claims):
    """Check quoted premises with a small trained NLI model, without truncation."""
    import os,torch
    from pathlib import Path
    from .inference_runtime_service import TextModelRuntime,gpu_stage,model_inputs,run_batches
    runtime=TextModelRuntime();proofs=[]
    try:
        with gpu_stage(),torch.inference_mode():
            location=Path(os.getenv('NLI_MODEL_PATH','scratch/a3-models/nli-deberta-v3-xsmall'))
            revision=json.loads((location/'source_revision.json').read_text(encoding='utf-8'))
            if revision!=dict(model=NLI_MODEL_ID,revision=NLI_REVISION):raise ValueError('NLI checkpoint revision mismatch')
            tokenizer,network=runtime.get(str(location.resolve()),True)
            if tuple(network.config.id2label[i] for i in range(3))!=NLI_LABELS:raise ValueError('NLI label mapping mismatch')
            pairs=[];bindings=[]
            for claim in claims:
                proof=dict(id=claim['id'],schema=NLI_SCHEMA,model=NLI_MODEL_ID,revision=NLI_REVISION,
                           claim_digest=source_claim_digest(claim),affirmed=[],negated=[])
                premise=claim['source']+('\n\n'+claim['target_source'] if claim.get('target_source') else '')
                for polarity in ('affirmed','negated'):
                    for hypothesis in relation_hypotheses(claim,polarity):
                        if len(tokenizer(premise,hypothesis,truncation=False)['input_ids'])>512:
                            proof['reason']='source_entailment_context_budget_exceeded';continue
                        pairs.append((premise,hypothesis));bindings.append((proof,polarity))
                proofs.append(proof)
            def score(batch):
                inputs=tokenizer([p[0] for p in batch],[p[1] for p in batch],padding=True,truncation=False,return_tensors='pt')
                return network(**model_inputs(inputs,network)).logits.float().softmax(-1).cpu().tolist()
            for (proof,polarity),values in zip(bindings,run_batches(pairs,8,score,torch)):
                proof[polarity].append(dict(zip(NLI_LABELS,values)))
        return proofs
    finally:runtime.park()


def infer_relation_claims(claims,predictor=None,entailment_scorer=None):
    """Review relation proposals with the existing lightweight GLiNER2 model."""
    if (not isinstance(claims,list) or len(claims)>512 or len({c.get('id') for c in claims})!=len(claims)):
        raise ValueError('Invalid relation review batch')
    for claim in claims:
        if (any(not isinstance(claim.get(k),str) or not claim[k].strip() for k in ('id','head','tail','predicate','source'))
                or claim['head'] not in claim['source']
                or claim['tail'] not in (claim.get('target_source') or claim['source'])):
            raise ValueError('Relation review endpoints must occur in original quotations')
    def review_all(model):
        decisions=[]
        for claim in claims:
            relationship=claim['head']+' -- '+claim['predicate']+' --> '+claim['tail']
            quoted='Source passage:\n'+claim['source']
            if claim.get('target_source'):quoted+='\n\nTarget source passage:\n'+claim['target_source']
            proposed='Proposed directed relationship:\n'+relationship
            if len((quoted+' '+proposed).split())>1800:
                decisions.append(dict(id=claim['id'],status='unresolved',reason='review_context_budget_exceeded',
                                      scores=[],raw_outputs=[]));continue
            raw=[model.classify_text(text,{'relation_support':dict(labels=RELATION_SUPPORT_LABELS,
                    multi_label=True,class_act='softmax',cls_threshold=0.,top_k=len(RELATION_SUPPORT_LABELS))},
                    include_confidence=True,max_len=2048)
                 for text in (quoted+'\n\n'+proposed,proposed+'\n\n'+quoted)]
            scores=[read_scores(r,task='relation_support',labels=RELATION_SUPPORT_LABELS) for r in raw]
            status,reason=relation_claim_verdict(scores)
            endpoints='Entity A: '+claim['head']+'\nEntity B: '+claim['tail']
            kind_raw=[model.classify_text(text,{'source_relation_kind':dict(labels=RELATION_KIND_LABELS,
                multi_label=True,class_act='softmax',cls_threshold=0.,top_k=4)},include_confidence=True,max_len=2048)
                for text in (quoted+'\n\n'+endpoints,endpoints+'\n\n'+quoted)]
            decision=dict(id=claim['id'],status=status,reason=reason,scores=scores,raw_outputs=raw,
                relation_kind_digest=source_claim_digest(claim),relation_kind_raw_outputs=kind_raw,
                relation_kind_scores=[read_scores(r,task='source_relation_kind',labels=RELATION_KIND_LABELS) for r in kind_raw])
            if status in {'affirmed','negated'} and not direct_relation_supported(decision,claim):
                decision.update(status='unresolved',reason='information_about_or_no_direct_relation')
            decisions.append(decision)
        return dict(schema=RELATION_REVIEW_SCHEMA,model=MODEL_ID,revision=REVISION,decisions=decisions,
                    policy='uncalibrated_model_review_not_human_verification')
    result=run_with_classifier(review_all,predictor) if claims else dict(schema=RELATION_REVIEW_SCHEMA,
        model=MODEL_ID,revision=REVISION,decisions=[])
    if claims:
        proofs=(entailment_scorer or infer_source_entailment)(claims)
        if len(proofs)!=len(claims) or {p['id'] for p in proofs}!={c['id'] for c in claims}:
            raise ValueError('Incomplete source entailment review')
        by_id={p['id']:p for p in proofs};by_claim={c['id']:c for c in claims}
        for decision in result['decisions']:
            proof=by_id[decision['id']];decision['source_entailment']=proof
            if decision['status'] in {'affirmed','negated'} and not source_entailment_supported(proof,decision['status'],by_claim[decision['id']]):
                decision.update(status='unresolved',reason='quoted_source_does_not_entail_directed_claim')
    return result


def passage_link_supported(decision):
    scores=decision.get('scores')
    return (isinstance(scores,list) and len(scores)==2 and all(isinstance(s,dict)
        and set(s)==set(PASSAGE_LINK_LABELS)
        and all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=1 for v in s.values())
        and s['specific_subject_link']>=.9
        and s['specific_subject_link']-max(v for k,v in s.items() if k!='specific_subject_link')>=.1 for s in scores))


def passage_pair_digest(pair):
    return hashlib.sha256(json.dumps([pair['source'],pair['target']],ensure_ascii=False).encode()).hexdigest()


def infer_passage_links(pairs,predictor=None):
    if (not isinstance(pairs,list) or len(pairs)>128 or len({p.get('id') for p in pairs})!=len(pairs)
            or any(any(not isinstance(p.get(k),str) or not p[k].strip() for k in ('id','source','target')) for p in pairs)):
        raise ValueError('Invalid passage review batch')
    def review(model):
        decisions=[]
        for pair in pairs:
            texts=['Passage A:\n'+a+'\n\nPassage B:\n'+b for a,b in
                   ((pair['source'],pair['target']),(pair['target'],pair['source']))]
            if any(len(text.split())>1800 for text in texts):
                decisions.append(dict(id=pair['id'],pair_digest=passage_pair_digest(pair),accepted=False,reason='context_budget_exceeded',scores=[]));continue
            raw=[model.classify_text(text,{'passage_link':dict(labels=PASSAGE_LINK_LABELS,multi_label=True,
                 class_act='softmax',cls_threshold=0.,top_k=4)},include_confidence=True,max_len=2048) for text in texts]
            decision=dict(id=pair['id'],pair_digest=passage_pair_digest(pair),scores=[read_scores(value,task='passage_link',labels=PASSAGE_LINK_LABELS) for value in raw],raw_outputs=raw)
            decision.update(accepted=passage_link_supported(decision))
            decision['reason']='specific_subject_link' if decision['accepted'] else 'no_consistent_specific_subject_support'
            decisions.append(decision)
        return dict(schema=PASSAGE_REVIEW_SCHEMA,model=MODEL_ID,revision=REVISION,decisions=decisions)
    return run_with_classifier(review,predictor) if pairs else dict(schema=PASSAGE_REVIEW_SCHEMA,model=MODEL_ID,revision=REVISION,decisions=[])


def request_passage_links(pairs):
    import requests
    from django.conf import settings
    response=requests.post(settings.RAG_INFERENCE_URL.rstrip('/')+'/rag/gliner2_passages',json=dict(pairs=pairs),timeout=(5,600))
    response.raise_for_status()
    result=response.json()
    if result.get('schema')!=PASSAGE_REVIEW_SCHEMA or result.get('model')!=MODEL_ID or result.get('revision')!=REVISION:
        raise ValueError('Passage review runtime is outdated or invalid')
    return result


def identity_name_key(name):
    """Name equality requested by the user; no aliases or fuzzy similarity."""
    return ' '.join(unicodedata.normalize('NFKC',name).casefold().split())
LABELS={
    'same_entity':'These same-name occurrences refer to the same entity in the supplied context and scope. Consider the subject, section, parent image and version. Sharing a name alone is insufficient; being related is not identity.',
    'different_entity':'Despite the same name, these occurrences refer to distinct entities, subjects, incompatible versions or scopes.',
    'uncertain':'The source contexts do not establish whether these same-name occurrences identify the same entity or different entities.',
}


def identity_occurrence(value):
    """Resolve the exact occurrence inside the supplied, unmodified quotation."""
    name=value.get('name');context=value.get('context')
    if not isinstance(name,str) or not name.strip() or not isinstance(context,str) or name not in context:
        raise ValueError('Identity name must occur exactly in its quoted source')
    if len(context)>2500:
        raise ValueError('Source context exceeds identity limit')
    scope=value.get('scope') or {}
    if any(k in scope for k in ('mention_start','mention_end','quote_start')):
        start,end,base=(scope.get(k) for k in ('mention_start','mention_end','quote_start'))
        if (any(type(v) is not int for v in (start,end,base)) or base<0
                or not 0<=start-base<end-base<=len(context) or context[start-base:end-base]!=name):
            raise ValueError('Identity occurrence offsets do not match its source quotation')
        return start-base,end-base
    start=context.index(name)
    return start,start+len(name)


def identity_context_available(value):
    # This is an evidence-sufficiency check, not a lexical entity classifier.
    # Repeating the same name and punctuation adds no disambiguating evidence.
    context=value['context'].replace(value['name'],'')
    return any(character.isalnum() for character in context)


def identity_text(pair,reverse=False):
    """Label the two existing source quotes without inventing bridging facts."""
    sides=('right','left') if reverse else ('left','right')
    parts=[]
    for index,side in enumerate(sides,1):
        value=pair.get(side,{})
        start,end=identity_occurrence(value)
        name=value['name'];context=value['context']
        parts.append(f'Mention {index}: {name}\nSource quotation {index}: {context}')
        parts.append(f'Mention character range {index}: [{start}, {end}) within source quotation {index}')
        if value.get('scope'):
            scope={k:value['scope'][k] for k in ('document_id','version_id','page','source_id',
                'reading_stream_id','parent_stream_id','heading_path',
                'mention_start','mention_end','quote_start') if k in value['scope']}
            parts.append('Source provenance '+str(index)+': '+json.dumps(scope,ensure_ascii=False,separators=(',',':')))
    return '\n\n'.join(parts)


def read_scores(result,task='entity_identity',labels=LABELS):
    rows=result.get(task)
    if not isinstance(rows,list) or len(rows)!=len(labels):
        raise ValueError('Classifier must return every actual label score')
    scores={}
    for row in rows:
        label=row.get('label');score=row.get('confidence')
        if label not in labels or label in scores or isinstance(score,bool) or not isinstance(score,(int,float)) or not math.isfinite(score) or not 0<=score<=1:
            raise ValueError('Invalid identity label scores')
        scores[label]=float(score)
    return scores


# The multilingual checkpoint scores "same" no higher than about .8, so the English model's .9 floor decided
# nothing. Measured on 122 pairs with known answers (unique public bodies within and across laws; "Bên A"/"Bên B"
# naming the same or different companies), using the weaker of the two orders of same minus different:
# >= 0 merged 109 of 112 true pairs and none of 10 different ones; every different pair was at -.09 or below,
# and <= -.2 kept 5 of them apart without splitting any true pair. Between the two stays unresolved.
SAME_MARGIN=0.
DIFFERENT_MARGIN=-.2


def margins(scores):
    return [s['same_entity']-s['different_entity'] for s in scores]


def decide(scores):
    if any(max(s,key=s.get)=='uncertain' for s in scores):
        return 'unresolved','model_uncertain'
    values=margins(scores)
    if min(values)>=SAME_MARGIN:
        return 'same','bidirectional_model_decision'
    if max(values)<=DIFFERENT_MARGIN:
        return 'different','bidirectional_model_decision'
    if min(values)<0<=max(values):
        return 'unresolved','orientation_disagreement'
    return 'unresolved','insufficient_confidence'


def decision_supported(row,status):
    """A stored decision must follow from its own scores under the margins above."""
    from .gliner_entity_service import valid_score
    if 'scores_forward' in row and 'scores_reverse' in row:
        scores=[row['scores_forward'],row['scores_reverse']]
        if not all(valid_score(s.get(k),0.) for s in scores for k in ('same_entity','different_entity')):return False
        return decide(scores)[0]==status
    same,different=row.get('same'),row.get('different')
    if not valid_score(same,0.) or not valid_score(different,0.):return False
    return same-different>=SAME_MARGIN if status=='same' else same-different<=DIFFERENT_MARGIN


def classify_pair(pair,predictor):
    identity_text(pair)
    if identity_name_key(pair['left']['name'])!=identity_name_key(pair['right']['name']):
        raise ValueError('Identity comparison requires the same entity name')
    tasks={'entity_identity':dict(labels=LABELS,multi_label=True,class_act='softmax',cls_threshold=0.,top_k=3)}
    raw=[predictor.classify_text(identity_text(pair,reverse=reverse),tasks,
            include_confidence=True,max_len=1024) for reverse in (False,True)]
    scores=[read_scores(r) for r in raw]
    status,reason=decide(scores)
    checks=[dict(side=side,context_available=identity_context_available(pair[side]))
            for side in ('left','right')]
    if not all(check['context_available'] for check in checks):
        status='unresolved';reason='insufficient_source_context'
    return dict(id=pair['id'],status=status,reason=reason,model=MODEL_ID,revision=REVISION,
        scores_forward=scores[0],scores_reverse=scores[1],raw_outputs=raw,
        reference_checks=checks,
        policy='unvalidated_model_proposal_no_graph_write')


# Each request loads GLiNER2 and releases it again, so a request carries as many pairs as passage review does.
IDENTITY_BATCH=128


def infer_pairs(pairs, predictor=None):
    """Production adapter; keep all actual scores and reject invalid batches."""
    if (not isinstance(pairs,list) or len(pairs)>IDENTITY_BATCH
            or any(not isinstance(p,dict) or not isinstance(p.get('id'),str) for p in pairs)
            or len({p['id'] for p in pairs})!=len(pairs)):
        raise ValueError('Invalid identity batch')
    for pair in pairs:
        identity_text(pair)
        if identity_name_key(pair['left']['name'])!=identity_name_key(pair['right']['name']):
            raise ValueError('Identity comparison requires the same entity name')
    # One text at a time: on 64 real pairs batches of 2 to 16 ran no faster (9.5 to 38.6 s against 10.0 s),
    # because each pair text already fills the GPU and batching only adds padding.
    def classify_all(model):
        decisions=[]
        for pair in pairs:
            row=classify_pair(pair,model)
            row['same']=min(s['same_entity'] for s in (row['scores_forward'],row['scores_reverse']))
            row['different']=max(s['different_entity'] for s in (row['scores_forward'],row['scores_reverse']))
            decisions.append(row)
        return dict(model=MODEL_ID,revision=REVISION,schema=SCHEMA,decisions=decisions)
    return run_with_classifier(classify_all,predictor) if pairs else classify_all(predictor)


def run_with_classifier(operation,predictor=None):
    """Share the existing classifier loader and release owned GPU weights."""
    owned=predictor is None
    if owned:
        import os
        from gliner2 import GLiNER2
        # fp16 ("quantize" in GLiNER2): about twice as fast as fp32 on this GPU. The margins and thresholds were
        # measured in fp32 and checked against fp16 on the same pairs and heading blocks before it was kept;
        # GLINER2_QUANTIZE=false restores full precision. Each endpoint releases Surya and GLiNER before loading.
        predictor=GLiNER2.from_pretrained(os.getenv('GLINER2_MODEL_PATH',MODEL_PATH),map_location='cuda',
            quantize=os.getenv('GLINER2_QUANTIZE','true').lower()=='true',local_files_only=True).eval()
    try:
        return operation(predictor)
    finally:
        if owned and predictor is not None:
            # Never leave this checkpoint competing with OCR/NER on a 4 GB GPU.
            del predictor
            import gc
            import torch
            gc.collect()
            torch.cuda.empty_cache()


def request_identity_pairs(pairs):
    import requests
    from django.conf import settings
    response=requests.post(settings.RAG_INFERENCE_URL.rstrip('/')+'/rag/gliner2_identity',
        json=dict(pairs=pairs),timeout=(5,600))
    response.raise_for_status()
    result=response.json()
    if (result.get('model')!=MODEL_ID or result.get('revision')!=REVISION
            or result.get('schema')!=SCHEMA or len(result.get('decisions',[]))!=len(pairs)
            or {r['id'] for r in result['decisions']}!={p['id'] for p in pairs}):
        raise ValueError('Invalid GLiNER2 identity runtime response')
    return result


import hashlib
from collections import defaultdict
from uuid import uuid5,NAMESPACE_URL
PREGRAPH_IDENTITY_SCHEMA='generic-entity-local-compaction-v2-grounded-context'
IDENTITY_TYPES={'ENTITY'}


def merge_contract_names(tree):
    """A contract uses a repeated name for one thing, so only GLiNER2's explicit 'different' keeps two apart."""
    identity=tree.get('identity_resolution') or {}
    entities=(tree.get('knowledge_graph') or {}).get('entities',[])
    if (tree.get('contract_clauses') or {}).get('status')!='complete' or identity.get('status')!='complete':return 0
    position={(e.get('source_id'),e.get('start')):e for e in entities}
    pairs={p['id']:p for p in identity.get('pairs',[])}
    apart=set()
    for row in identity.get('decisions',[]):
        if row.get('status')=='different':
            left,right=[position.get((pairs[row['id']][side]['scope']['source_id'],pairs[row['id']][side]['scope']['mention_start'])) for side in ('left','right')]
            if left and right:apart.add(frozenset((left['canonical_key'],right['canonical_key'])))
    kept={};moved={}
    for entity in entities:
        canonical=entity.get('canonical_key')
        if not canonical or canonical in moved:continue
        group=kept.setdefault(identity_name_key(entity['name']),[])
        target=next((c for c in group if c==canonical or frozenset((c,canonical)) not in apart),None)
        if target is None:group.append(canonical)
        elif target!=canonical:moved[canonical]=target
    for entity in entities:
        if entity.get('canonical_key') in moved:
            entity.update(canonical_key=moved[entity['canonical_key']],identity_resolution_status='contract_name_merged')
    identity.update(canonical_entities=len({e.get('canonical_key') for e in entities}),contract_merged_groups=len(moved))
    return len(moved)


# Differently written names ("Uy ban"/"Ủy ban", "Toà"/"Tòa"). Fusion of shared words and BGE proposes,
# the reranker scores, and GLiNER2 may only refuse after reading both passages. Measured on Hộ tịch and
# Trọng tài: rerank >= 9 merged 6 true pairs and no false one; 8 already joined "Hội đồng"~"Hiệp hội".
LOOK_ALIKE_RERANK=9.
LOOK_ALIKE_NEIGHBOURS=3


def find_similar_names(names):
    """names: [(key, text)] -> [(key, key, rerank score)] for the fused nearest names."""
    if len(names)<2:return []
    import numpy
    from shared.retrieval import tokens
    from .contract_pipeline_service import HybridBackend
    from .passage_reference_service import request_rerank
    keys=[k for k,_ in names];texts=[t for _,t in names]
    vectors=numpy.asarray(HybridBackend().embedding(texts),dtype=float)
    vectors/=numpy.linalg.norm(vectors,axis=1,keepdims=True).clip(min=1e-12)
    similarity=vectors@vectors.T
    words=[set(tokens(t)) for t in texts]
    found=set()
    for i in range(len(keys)):
        dense=[int(j) for j in numpy.argsort(-similarity[i]) if j!=i][:20]
        lexical=sorted((j for j in range(len(keys)) if j!=i and words[i]&words[j]),
            key=lambda j:-len(words[i]&words[j])/len(words[i]|words[j]))[:20]
        fused=defaultdict(float)
        for stream in (dense,lexical):
            for rank,j in enumerate(stream,1):fused[j]+=1/(60+rank)
        for j in sorted(fused,key=lambda j:-fused[j])[:LOOK_ALIKE_NEIGHBOURS]:found.add(tuple(sorted((i,j))))
    found=sorted(found)
    scores=request_rerank([[texts[i],texts[j]] for i,j in found])
    return [(keys[i],keys[j],float(s)) for (i,j),s in zip(found,scores)]


def renamed(side,name):
    """The same passage with its mention written as name, so GLiNER2 compares context, not spelling."""
    scope=dict(side['scope'])
    start=scope['mention_start']-scope['quote_start'];end=scope['mention_end']-scope['quote_start']
    scope['mention_end']=scope['mention_start']+len(name)
    return dict(side,name=name,context=side['context'][:start]+name+side['context'][end:],scope=scope)


def resolve_identities(run,tree,request_model=None,propose_names=find_similar_names):
    from .gliner_entity_service import valid_score
    request_model=request_model or request_identity_pairs
    company=run.version.contract.company_id
    leaves={l['chunk_id']:l for l in tree['leaves']}
    entities=tree.get('knowledge_graph',{}).get('entities',[])
    mentions=[]
    for entity in entities:
        entity['entity_type']='ENTITY'
        source=next((leaves[i] for i in entity['source_ids'] if i in leaves and entity['name'] in leaves[i]['text']),None)
        if source is None:raise ValueError('Identity mention has no grounded original source')
        text=source['text'];position=entity.get('start')
        if type(position) is not int:
            position=text.find(entity['name'])
        if text[position:position+len(entity['name'])]!=entity['name']:
            raise ValueError('Identity occurrence offsets do not match its original source')
        start=max(0,position-250);end=min(len(text),max(position+len(entity['name']),start+900))
        scope=dict(company_id=company,document_id=f'contract-version-{run.version_id}',
            version_id=run.version_id,run_id=run.pk,page=source.get('page_number'),
            region=source.get('bbox'),source_id=source['chunk_id'],
            reading_stream_id=source.get('reading_stream_id'),
            source_reading_stream_id=source.get('source_reading_stream_id'),
            parent_stream_id=source.get('parent_reading_stream_id'),heading_path=source.get('heading_path',[]),
            mention_start=position,mention_end=position+len(entity['name']),quote_start=start)
        mentions.append(dict(key=entity['key'],name=entity['name'],kind=entity['entity_type'],
            source_ids=list(entity['source_ids']),scope=scope,context=text[start:end],
            quote_start=start,quote_end=end,source_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
            canonical_key=str(uuid5(NAMESPACE_URL,json.dumps([company,run.version_id,run.pk,entity['key']])))))
    nodes={m['key']:m for m in mentions};pairs={};bindings=defaultdict(list)
    def add(left,right):
        a,b=left,right
        if a['key']>b['key']:a,b=b,a
        # Only identical model inputs share inference; every occurrence binding
        # is retained even across pages/streams or registered documents.
        sides=[dict(name=m['name'],context=m['context'],scope=m['scope']) for m in (a,b)]
        # "Bộ Tư pháp" against "bộ tư pháp": both passages carry one spelling, so GLiNER2 compares only the
        # context, as for look-alike names. Shown as written, the two orders disagreed on 48 of 577 pairs.
        if sides[1]['name']!=sides[0]['name']:
            sides[1]=renamed(sides[1],sides[0]['name'])
        identity=hashlib.sha256(json.dumps([a['kind'],sides],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        pairs.setdefault(identity,dict(id=identity,entity_type=a['kind'],left=sides[0],right=sides[1]))
        bindings[identity].append((a['key'],b['key']))
        return identity
    verdicts={}
    def ask(batch):
        for offset in range(0,len(batch),IDENTITY_BATCH):
            part=batch[offset:offset+IDENTITY_BATCH];response=request_model(part)
            decisions=response.get('decisions',[])
            if len(decisions)!=len(part) or {d['id'] for d in decisions}!={p['id'] for p in part}:
                raise ValueError('Incomplete pregraph identity response')
            for row in decisions:
                if row.get('status') not in {'same','different','unresolved'}:
                    raise ValueError('Invalid identity decision')
                verdicts[row['id']]=row
            print(json.dumps(dict(event='pregraph_identity_batch',run_id=run.pk,model=MODEL_ID,
                completed_pairs=len(verdicts),total_pairs=len(pairs),
                accepted_same=sum(d['status']=='same' and all(identity_context_available(pairs[i][side])
                    for side in ('left','right')) for i,d in verdicts.items()))),flush=True)
    # Equal names only. A mention is compared with one member of each group found so far: when A
    # matches B and B matches C, GLiNER2 need not read A against C, and a long law repeats a name often.
    named=defaultdict(list)
    for mention in mentions:named[(mention['kind'],identity_name_key(mention['name']))].append(mention)
    leaders={name:[group[0]] for name,group in named.items()}
    waiting=[dict(mention=m,name=name,tried=0) for name,group in named.items() for m in group[1:]]
    while waiting:
        asked={}
        for row in waiting:
            row['identity']=None
            if row['tried']<len(leaders[row['name']]):
                row['identity']=add(row['mention'],leaders[row['name']][row['tried']])
                if row['identity'] not in verdicts:asked[row['identity']]=pairs[row['identity']]
        ask(list(asked.values()))
        unsettled=[];promoted=set()
        for row in waiting:
            if row['identity'] is None:
                # One new leader per name each round; the others are compared with it next.
                if row['name'] in promoted:
                    unsettled.append(row)
                else:
                    promoted.add(row['name'])
                    leaders[row['name']].append(row['mention'])
                continue
            # Only a clear difference earns another comparison; merge_contract_names treats anything else as one thing.
            verdict=verdicts[row['identity']]
            usable=all(identity_context_available(pairs[row['identity']][side]) for side in ('left','right'))
            if verdict['status']!='different' or not usable:continue
            row['tried']+=1
            unsettled.append(row)
        waiting=unsettled
    look_alike=[]
    firsts={name:group[0] for name,group in leaders.items()}
    proposals=[(a,b,s) for a,b,s in propose_names([(name,m['name']) for name,m in firsts.items()])
        if s>=LOOK_ALIKE_RERANK and a[0]==b[0] and a!=b]
    asked={}
    for a,b,score in proposals:
        left,right=firsts[a],firsts[b]
        sides=[dict(name=left['name'],context=left['context'],scope=left['scope']),
            renamed(dict(name=right['name'],context=right['context'],scope=right['scope']),left['name'])]
        identity=hashlib.sha256(json.dumps(['look_alike',left['kind'],sides],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        pairs.setdefault(identity,dict(id=identity,entity_type=left['kind'],left=sides[0],right=sides[1]))
        bindings[identity].append((left['key'],right['key']))
        look_alike.append(dict(pair_id=identity,names=[left['name'],right['name']],rerank=score))
        if identity not in verdicts:asked[identity]=pairs[identity]
    ask(list(asked.values()))
    requests=list(pairs.values())
    parent={key:key for key in nodes}
    def root(key):
        while key!=parent[key]:parent[key]=parent[parent[key]];key=parent[key]
        return key
    prohibited=[];positive=[];rejections=[]
    look_alike_ids={row['pair_id'] for row in look_alike}
    for row in look_alike:
        verdict=verdicts[row['pair_id']];row['gliner2']=verdict['status']
        refused=verdict['status']=='different' and all(identity_context_available(pairs[row['pair_id']][side]) for side in ('left','right'))
        row['merged']=not refused
        if refused:
            if not decision_supported(verdict,'different'):raise ValueError('Identity difference without valid model scores')
            continue
        positive.extend((-1.,a,b,row['pair_id']) for a,b in bindings[row['pair_id']])
    for identity,row in verdicts.items():
        same,different=row.get('same'),row.get('different')
        context_available=all(identity_context_available(side) for side in
            (pairs[identity]['left'],pairs[identity]['right']))
        if row['status'] in {'same','different'} and not context_available:
            rejections.append(dict(pair_id=identity,reason='insufficient_source_context'))
            continue
        if identity in look_alike_ids:continue
        if row['status']=='same':
            if not decision_supported(row,'same'):
                raise ValueError('Identity acceptance without valid model scores')
            for a,b in bindings[identity]:positive.append((same,a,b,identity))
        elif row['status']=='different':
            if not decision_supported(row,'different'):
                raise ValueError('Identity difference without valid model scores')
            prohibited.extend(bindings[identity])
    for score,a,b,identity in sorted(positive,reverse=True):
        ra,rb=root(a),root(b)
        if ra==rb:continue
        if any({root(x),root(y)}=={ra,rb} for x,y in prohibited):
            rejections.append(dict(pair_id=identity,reason='contradictory_model_difference'));continue
        parent[max(ra,rb)]=min(ra,rb)
    components=defaultdict(list)
    for key in nodes:components[root(key)].append(nodes[key])
    assignments={};groups=[]
    for members in components.values():
        local=members
        if not local:continue
        canonical=min(m['canonical_key'] for m in local)
        linked=len(local)>1
        for mention in local:assignments[mention['key']]=dict(canonical_key=canonical,
            identity_resolution_status='model_linked' if linked else 'unresolved' if any(mention['key'] in pair for rows in bindings.values() for pair in rows) else 'separate',
            identity_model=MODEL_ID,identity_revision=REVISION,
            identity_name_key=identity_name_key(mention['name']),identity_schema=PREGRAPH_IDENTITY_SCHEMA)
        groups.append(dict(canonical_key=canonical,mention_keys=[m['key'] for m in local],
            registered_identity=False,name=local[0]['name']))
    for entity in entities:
        if entity['key'] in assignments:
            entity.update(assignments[entity['key']])
    result=dict(schema=PREGRAPH_IDENTITY_SCHEMA,classifier_schema=SCHEMA,status='complete',model=MODEL_ID,revision=REVISION,
        source_fingerprint=tree.get('source_fingerprint'),mentions=len(mentions),
        linked=sum(a['identity_resolution_status']=='model_linked' for a in assignments.values()),
        unresolved=sum(a['identity_resolution_status']=='unresolved' for a in assignments.values()),
        canonical_entities=len(groups),groups=groups,
        source_mentions=[{k:v for k,v in m.items() if k!='embedding'} for m in mentions],
        pairs=requests,decisions=list(verdicts.values()),rejected=rejections,look_alike=look_alike,
        candidate_policy='same_name_and_reranked_look_alike_names',scope='document_version_and_run',graph_nodes_saved=len(mentions)-len(groups),
        policy='Only equal names with source context beyond the name may merge; every merge additionally requires GLiNER2 context approval; accepted groups share one graph node; occurrence provenance is retained on source links')
    tree['identity_resolution']=result
    return result
