"""Project source-grounded structure and model-proposed knowledge into Neo4j."""
import math
from pathlib import Path
import hashlib
import json
from django.conf import settings
from ai_extract import SEMANTIC_RELATIONS, SEMANTIC_EDGE_TYPES, STRUCTURE_REVIEW_SCHEMA
from ai_extract.repositories import document_graph_repository as repository

SOURCE_RELATIONS={'NEXT','CONTAINS','HAS_EVIDENCE','HAS_ROW','HAS_CELL','HAS_VISUAL','APPEARS_IN','LEFT_OF','ABOVE'}


def relation_review_key(edge):
    return hashlib.sha256(json.dumps([edge.get(k,'') for k in
        ('from_key','to_key','type','origin','source_leaf_id')],ensure_ascii=False).encode()).hexdigest()


def structure_review_fingerprint(tree,edges):
    return hashlib.sha256(json.dumps([STRUCTURE_REVIEW_SCHEMA,tree.get('source_fingerprint'),
        sorted((n['id'],n.get('parent_id'),n.get('kind'),n.get('title')) for n in tree.get('nodes',[])),
        sorted(relation_review_key(e) for e in edges if e['type'] in SOURCE_RELATIONS)]).encode()).hexdigest()


def review_surya_relations(run,request_model=None):
    """Account for every structural edge; semantic model abstention is explicit.

    Text-only GLiNER cannot certify geometry or source ownership. Those receive
    integrity checks. Reading/section proposals with source text on both sides
    receive a separate model review, never an invented fallback verdict.
    """
    from .gliner_entity_service import request_structure_pairs
    tree=run.structure
    _,nodes,all_edges=projection(run,tree,include_review=False)
    edges=[e for e in all_edges if e['type'] in SOURCE_RELATIONS]
    fingerprint=structure_review_fingerprint(tree,edges)
    previous=tree.get('structure_review',{})
    if previous.get('fingerprint')==fingerprint and previous.get('status')=='complete':return previous
    node_map={n['key']:n for n in nodes};sources={l['chunk_id']:l for l in tree['leaves']}
    texts={n['key']:n['text'] for n in nodes if n.get('category')=='evidence'}
    for edge in all_edges:
        if edge['type']=='HAS_EVIDENCE' and edge['to_key'] in texts:
            texts.setdefault(edge['from_key'],texts[edge['to_key']])
    for node in nodes:
        if node.get('category')=='structure' and node.get('title'):
            title=node['title']
            if any(title in leaf['text'] for leaf in sources.values()):texts[node['key']]=title
    reviews={};pairs={};pair_edges={}
    cached=previous.get('relations',{}) if previous.get('fingerprint')==fingerprint else {}
    for edge in edges:
        key=relation_review_key(edge)
        valid=(edge['from_key'] in node_map and edge['to_key'] in node_map
               and (not edge.get('source_leaf_id') or edge['source_leaf_id'] in sources))
        if valid and edge['type']=='HAS_EVIDENCE':
            valid=node_map[edge['to_key']].get('leaf_id') in sources
        if valid and edge['type'] in {'LEFT_OF','ABOVE'}:
            try:
                boxes=[json.loads(node_map[edge[k]].get('bbox_json','null')) for k in ('from_key','to_key')]
                valid=all(isinstance(b,list) and len(b)==4 and all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in b)
                          and b[0]<b[2] and b[1]<b[3] for b in boxes)
                if valid:
                    a,b=boxes
                    valid=a[2]<=b[0] if edge['type']=='LEFT_OF' else a[3]<=b[1]
            except (ValueError,TypeError):valid=False
        review=dict(type=edge['type'],from_key=edge['from_key'],to_key=edge['to_key'],
                    integrity='valid' if valid else 'invalid',status='integrity_checked',origin='source_integrity')
        if not valid:review['status']='invalid'
        elif edge['type'] in {'NEXT','CONTAINS'}:
            left,right=texts.get(edge['from_key'],''),texts.get(edge['to_key'],'')
            if left.strip() and right.strip():
                review.update(status='pending',origin='gliner_structure_review')
                if cached.get(key,{}).get('status') in {'supported','disputed','unresolved'}:
                    review=cached[key]
                else:
                    signature=(edge['type'],left[:1800],right[:1800])
                    identity=hashlib.sha256(json.dumps(signature,ensure_ascii=False).encode()).hexdigest()
                    pairs.setdefault(identity,dict(id=identity,kind=edge['type'],left=signature[1],right=signature[2]))
                    pair_edges.setdefault(identity,[]).append(key)
            else:review.update(status='not_applicable',origin='source_integrity',reason='text_model_has_no_two_sided_source')
        reviews[key]=review
    pending=list(pairs.values());errors=[]
    enabled=request_model is not None or (getattr(settings,'A3_KNOWLEDGE_ENABLED',False)
        and getattr(settings,'A3_ENTITY_PROVIDER','disabled')=='gliner')
    if pending and not enabled:errors.append('gliner_disabled')
    for offset in range(0,len(pending) if enabled else 0,16):
        batch=pending[offset:offset+16]
        try:
            result=(request_model or request_structure_pairs)(batch)
            if len(result['decisions'])!=len(batch) or {r['id'] for r in result['decisions']}!={p['id'] for p in batch}:
                raise ValueError('Structure review pair coverage mismatch')
            for verdict in result['decisions']:
                if verdict.get('status') not in {'supported','disputed','unresolved'}:raise ValueError('Invalid structure verdict')
                for key in pair_edges[verdict['id']]:
                    reviews[key].update({k:v for k,v in verdict.items() if k!='id'})
        except Exception as error:
            errors.append(type(error).__name__);break
    counts={status:sum(r['status']==status for r in reviews.values()) for status in
            ('integrity_checked','not_applicable','supported','disputed','unresolved','pending','invalid')}
    tree['structure_review']=dict(schema=STRUCTURE_REVIEW_SCHEMA,fingerprint=fingerprint,
        status='partial' if errors else 'complete',relations=reviews,counts=counts,errors=errors,
        relations_total=len(edges),model_pairs=len(pairs),provider='gliner',
        policy='review_is_not_verified_structure; preserve_source_and_expose_uncertainty')
    return tree['structure_review']


def infer_relations(tree, request_model=None):
    """Use the single GLiNER extraction/validation path for semantic proposals."""
    if not getattr(settings, 'A3_KNOWLEDGE_ENABLED', False):
        return dict(status='disabled', entities=[], relations=[])
    if request_model is None and getattr(settings,'A3_ENTITY_PROVIDER','disabled')!='gliner':
        return dict(status='disabled', provider='source_layout', entities=[], relations=[],
                    reason='Structural and geometric graph only; no semantic model configured')
    from .gliner_entity_service import extract_graph_entities
    return extract_graph_entities(tree,request_model)


def graph_scope(run, tree):
    contract = run.version.contract
    scope = dict(company_id=contract.company_id, contract_id=contract.pk, version_id=run.version_id,
                 run_id=run.pk, fingerprint=tree.get('source_fingerprint', ''))
    if not scope['company_id'] or not scope['fingerprint']:
        raise ValueError('Graph requires tenant and source fingerprint')
    scope['key'] = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()
    return scope


def projection(run, tree, include_review=True):
    scope = graph_scope(run, tree)
    nodes, edges, seen_edges = [], [], set()
    def key(logical):
        return scope['key']+':'+logical
    def node(logical, **props):
        nodes.append(dict(key=key(logical), snapshot_key=scope['key'], **props))
    def edge(a, b, kind, predicate='', quote='', source='', origin='source_structure', **metadata):
        record=dict(from_key=key(a), to_key=key(b), type=kind, predicate=predicate,
                    quote=quote, source_leaf_id=source, origin=origin, **metadata)
        identity=json.dumps(record,sort_keys=True,ensure_ascii=False)
        if identity not in seen_edges:
            edges.append(record);seen_edges.add(identity)
    node_ids = {n['id'] for n in tree['nodes']}
    for n in tree['nodes']:
        node('node:'+n['id'], category='structure', title=n.get('title',''), kind=n['kind'],
             origin=n.get('structure_source','source_structure'))
        if n.get('parent_id') in node_ids:
            model_structure=n.get('structure_source','').startswith('surya')
            edge('node:'+n['parent_id'], 'node:'+n['id'], 'CONTAINS',
                 origin='surya_model_structure' if model_structure else 'source_structure',
                 review_status='unreviewed' if model_structure else 'source_extracted')
    leaf_ids = {l['chunk_id'] for l in tree['leaves']}
    for leaf in tree['leaves']:
        node('leaf:'+leaf['chunk_id'], category='evidence', leaf_id=leaf['chunk_id'],
             source_id=leaf.get('source_chunk_id',''), text=leaf['text'],
             page_number=leaf.get('page_number',1), bbox_json=json.dumps(leaf.get('bbox',[])),
             image_path=leaf.get('image_path',''),
             **{k:leaf[k] for k in ('reading_stream_id','reading_stream_kind','reading_stream_status',
                 'reading_stream_position','parent_reading_stream_id','reading_document_position') if k in leaf})
        # Ancestors reach this source through CONTAINS; bind only its nearest
        # owner instead of repeating the same evidence edge at every level.
        owner = next((a for a in reversed(leaf.get('ancestor_ids', [])) if a in node_ids), None)
        if owner is not None:
            predicted=(leaf.get('structure_metadata') or {}).get('layout_source')=='surya' and owner!='root'
            edge('node:'+owner, 'leaf:'+leaf['chunk_id'], 'HAS_EVIDENCE',
                 origin='surya_heading_sequence' if predicted else 'source_structure',
                 review_status='unreviewed' if predicted else 'source_extracted')
    originals = {l['chunk_id']:l for l in tree['leaves']}
    for rel in tree.get('relations', []):
        if rel.get('from_id') in leaf_ids and rel.get('to_id') in leaf_ids:
            edge('leaf:'+rel['from_id'], 'leaf:'+rel['to_id'], 'RELATED',
                 str(rel.get('kind', 'reference')), originals[rel['from_id']]['text'],
                 rel['from_id'], 'structure_model_relation_not_semantic_verification')
    knowledge = tree.get('knowledge_graph', {})
    entities = {e['key']:e for e in knowledge.get('entities', [])}
    entity_ids = entities.keys()
    for entity in knowledge.get('entities', []):
        typed=entity.get('origin')=='gliner_source_span'
        props=dict(entity_type=entity.get('entity_type'),kind=entity.get('entity_type','entity').lower(),
                   char_start=entity.get('start'),char_end=entity.get('end'),confidence=entity.get('confidence'),
                   review_status='unreviewed') if typed else {}
        node('entity:'+entity['key'], category='entity', name=entity['name'], origin=entity.get('origin','model_proposal_source_aligned'),**props)
        for source in entity['source_ids']:
            if source in leaf_ids:
                edge('leaf:'+source, 'entity:'+entity['key'], 'MENTIONS', source=source,
                     origin='gliner_source_span' if typed else 'source_structure',
                     review_status='unreviewed' if typed else 'source_extracted')
                # MENTIONS already binds the exact source span to this entity;
                # a reverse HAS_EVIDENCE edge would duplicate that binding.
    for rel in knowledge.get('relations', []):
        if rel['from_key'] in entity_ids and rel['to_key'] in entity_ids and rel['source_id'] in leaf_ids:
            if rel['predicate']=='references' and rel.get('target_source_id',rel['source_id'])!=rel['source_id']:
                continue  # Store this once as a source-to-source REFERENCES edge below.
            kind=SEMANTIC_RELATIONS.get(rel['predicate'],'RELATED') if rel.get('origin')=='gliner_relex_source_span' else 'RELATED'
            edge('entity:'+rel['from_key'], 'entity:'+rel['to_key'], kind, rel['predicate'],
                 rel['quote'], rel['source_id'], rel['origin'], review_status='unreviewed',confidence=rel.get('confidence'),
                 polarity=rel.get('polarity', 'unspecified'), modality=rel.get('modality', 'unspecified'),
                 condition_quotes=rel.get('condition_quotes', []), scope_quote=rel.get('scope_quote', rel['quote']),
                 qualification_quote=rel.get('qualification_quote', ''),
                 target_source_leaf_id=rel.get('target_source_id'),target_quote=rel.get('target_quote',''),
                 qualification_validation=rel.get('qualification_validation', 'legacy_unqualified'))
    for link in knowledge.get('source_relations',[]):
        if link['from_id'] in leaf_ids and link['to_id'] in leaf_ids:
            typed=link.get('origin')=='gliner_relex_source_span'
            kind=SEMANTIC_RELATIONS.get(link['kind'],'RELATED') if typed else 'RELATED'
            a,b=entities.get(link.get('from_key'),{}),entities.get(link.get('to_key'),{})
            edge('leaf:'+link['from_id'],'leaf:'+link['to_id'],kind,link['kind'],link['from_quote'],
                 link['from_id'],link['origin'], target_quote=link['to_quote'],review_status='unreviewed',
                 target_source_leaf_id=link['to_id'],confidence=link.get('confidence'),
                 from_char_start=a.get('start'),from_char_end=a.get('end'),to_char_start=b.get('start'),to_char_end=b.get('end'))
    visual=tree.get('visual_graph',{})
    image_ids={i['key'] for i in visual.get('images',[])}
    object_ids={o['key'] for o in visual.get('objects',[])}
    for image in visual.get('images',[]):
        node('image:'+image['key'],category='image',image_path=image['image_path'],sha256=image['sha256'],
             width=image['width'],height=image['height'],coordinate_frame='image_normalized_0_1000')
        for source in image['source_ids']:
            if source in leaf_ids: edge('leaf:'+source,'image:'+image['key'],'HAS_VISUAL',source=source)
    for obj in visual.get('objects',[]):
        node('object:'+obj['key'],category='visual_object',name=obj['name'],bbox_json=json.dumps(obj['bbox']),
             image_key=obj['image_key'],origin=obj['origin'],review_status='unreviewed')
        if obj['image_key'] in image_ids:
            edge('object:'+obj['key'],'image:'+obj['image_key'],'APPEARS_IN',origin=obj['origin'],review_status='unreviewed')
    for rel in visual.get('relations',[]):
        if rel['from_key'] in object_ids and rel['to_key'] in object_ids:
            edge('object:'+rel['from_key'],'object:'+rel['to_key'],rel['kind'],origin=rel['origin'],
                 threshold=rel.get('threshold'),review_status='unreviewed')
    for link in visual.get('text_links',[]):
        if link['source_id'] in leaf_ids and link['object_key'] in object_ids:
            edge('leaf:'+link['source_id'],'object:'+link['object_key'],'EXPLAINS',link['kind'],
                 link['quote'],link['source_id'],link['origin'],review_status='unreviewed')
    append_layout_edges(tree, node, edge)
    from .layout_extractor import colpali_point_id
    from .contract_pipeline_service import COLPALI_COLLECTION
    acknowledged = set(tree.get('colpali_point_ids', []))
    if acknowledged:
        for page in run.pages.prefetch_related('blocks').order_by('page_number'):
            for block in page.blocks.all():
                point_id = colpali_point_id(run.pk, page.pk, block.pk)
                logical = f'layout-block:{page.page_number}:block:{block.pk}'
                if (point_id not in acknowledged or block.layout_type != 'figure'
                        or not any(n['key'] == key(logical) for n in nodes)):
                    continue
                node('embedding:'+point_id, category='visual_embedding', page_number=page.page_number,
                     point_id=point_id, collection=COLPALI_COLLECTION, model='vidore/colpali-v1.2',
                     storage='qdrant', status='indexed')
                edge(logical, 'embedding:'+point_id, 'HAS_EMBEDDING', origin='qdrant_acknowledged_write')
    edges=compact_relations(edges)
    review=tree.get('structure_review',{})
    if include_review and review.get('fingerprint')==structure_review_fingerprint(tree,edges):
        for edge in edges:
            judgment=review.get('relations',{}).get(relation_review_key(edge))
            if judgment:
                if judgment['origin']=='gliner_structure_review':
                    edge.update(source_review_status=edge.get('review_status','unreviewed'),review_status='model_'+judgment['status'])
                edge.update(structure_review_status=judgment['status'],review_origin=judgment['origin'],
                            review_evidence_json=json.dumps(judgment.get('evidence',[]),ensure_ascii=False))
    return scope, nodes, [e for e in edges if e.get('structure_review_status')!='invalid']


def compact_relations(edges):
    """Remove redundant graph paths without inferring new semantic facts.

    Directional geometry and bounding boxes remain available. A generic
    association is redundant only when its full evidence and qualifiers match
    a specific assertion; sharing endpoints alone is not sufficient.
    """
    def assertion(edge):
        return json.dumps({k:v for k,v in edge.items() if k != 'type'},
                          sort_keys=True, ensure_ascii=False)
    specific = {assertion(e) for e in edges if e['type'] in SEMANTIC_EDGE_TYPES}
    rows = {}
    cells = {}
    for edge in edges:
        if edge['type'] == 'HAS_ROW':
            rows.setdefault(edge['from_key'], set()).add(edge['to_key'])
        elif edge['type'] == 'HAS_CELL':
            cells.setdefault(edge['from_key'], []).append(edge)
    def redundant_cell(edge):
        # Keep a direct binding if the row path has different provenance.
        for row in rows.get(edge['from_key'], ()):
            for child in cells.get(row, ()):
                if child['to_key'] == edge['to_key'] and all(
                        child.get(k) == v for k,v in edge.items() if k != 'from_key'):
                    return True
        return False
    return [e for e in edges if e['type'] != 'NEAR'
            and not (e['type'] == 'RELATED' and assertion(e) in specific)
            and not (e['type'] == 'HAS_CELL' and redundant_cell(e))]


def sync_graph(run,review_structure=False):
    tree = run.structure
    if not getattr(settings, 'A3_GRAPH_ENABLED', False):
        return dict(status='disabled')
    if not getattr(settings, 'NEO4J_URI', '') or not getattr(settings, 'NEO4J_PASSWORD', ''):
        return dict(status='not_configured')
    try:
        if not visual_sources_fresh(tree):
            return dict(status='stale_visual_source')
        if review_structure:review_surya_relations(run)
        scope, nodes, edges = projection(run, tree)
        repository.replace_snapshot(scope, nodes, edges)
        return dict(status='ready', fingerprint=scope['fingerprint'], nodes=len(nodes), edges=len(edges),
            structure_review=tree.get('structure_review',{}).get('status','not_requested'))
    except Exception as exc:
        return dict(status='unavailable', error_type=type(exc).__name__)


def cleanup_old_run_graphs(run):
    """Only a persisted completed run with a ready graph may retire history."""
    if run.status != 'COMPLETED' or run.structure.get('graph_index',{}).get('status') != 'ready':
        return dict(status='skipped', deleted_snapshots=0)
    try:
        scope=graph_scope(run,run.structure)
        if run.structure['graph_index'].get('fingerprint') != scope['fingerprint']:
            return dict(status='skipped_stale_graph',deleted_snapshots=0)
        return dict(status='completed',deleted_snapshots=repository.prune_old_runs(scope))
    except Exception as error:
        # Cleanup failure must not turn a successfully persisted extraction
        # into FAILED. A later successful run can retry the scoped deletion.
        return dict(status='failed',error_type=type(error).__name__)


def resolve_shared_entities(scope, embedding=None, request_model=None):
    """Incremental tenant registry, leaving assertions on their original occurrences.

    Only identity-bearing types participate. Amounts, dates, roles, conditions
    and obligations stay local to their contracts. No spelling/similarity rule
    is allowed to assert sameness; uncertain model pairs remain separate.
    """
    from uuid import uuid5, NAMESPACE_URL
    from shared.retrieval import tokens
    from .gliner_entity_service import request_identity_pairs, valid_score
    types={'ORGANIZATION','PERSON','PRODUCT','TAX_CODE','BANK_ACCOUNT','LOCATION'}
    mentions=[m for m in repository.entity_occurrences(scope) if m['entity_type'] in types]
    if not mentions:return dict(status='complete',mentions=0,linked=0,unresolved=0)
    if embedding is None:
        from .contract_pipeline_service import HybridBackend
        embedding=HybridBackend().embedding
    request_model=request_model or request_identity_pairs

    def window(name,text):
        position=text.find(name)
        if position<0:raise ValueError('Entity name is absent from its source')
        start=max(0,position-350)
        return text[start:max(position+len(name),start+1100)]

    rows=[]
    for m in mentions:
        source=next(s['text'] for s in m['sources'] if m['name'] in s['text'])
        m['context']=window(m['name'],source)
        m['context_hash']=hashlib.sha256((m['name']+'\0'+m['context']).encode()).hexdigest()
        lookup=hashlib.sha256(f"{scope['company_id']}:{m['entity_type']}".encode()).hexdigest()
        rows.append(dict(mention_key=m['mention_key'],name=m['name'],entity_type=m['entity_type'],
            lookup_scope=lookup,canonical_key=str(uuid5(NAMESPACE_URL,m['mention_key'])),context_hash=m['context_hash']))
    vectors={i:m['cached_embedding'] for i,m in enumerate(mentions)
             if m.get('cached_hash')==m['context_hash'] and len(m.get('cached_embedding') or [])==1024}
    missing=[i for i in range(len(mentions)) if i not in vectors]
    for offset in range(0,len(missing),32):
        repository.renew_entity_job(scope)
        positions=missing[offset:offset+32];batch=[mentions[i] for i in positions]
        values=embedding([m['name']+'\n'+m['context'] for m in batch])
        if len(values)!=len(batch) or any(len(v)!=1024 or any(not math.isfinite(float(x)) for x in v) for v in values):
            raise ValueError('Invalid entity embedding batch')
        vectors.update(zip(positions,values))
    for i,row in enumerate(rows):row['embedding']=vectors[i]
    registered={r['mention_key']:r['canonical_key'] for r in repository.register_entity_occurrences(scope,rows)}
    if set(registered)!={m['mention_key'] for m in mentions}:
        raise ValueError('Entity resolution snapshot is no longer current')
    pairs=[];pair_ids={};candidates={};parent={}
    for m,row in zip(mentions,rows):
        own=registered[m['mention_key']];parent.setdefault(own,own)
        words=tokens(m['name'])
        # Lucene query syntax is application-owned, not model-generated Cypher.
        terms=' OR '.join('"'+w.replace('\\','\\\\').replace('"','\\"')+'"' for w in words)
        query='lookup_scope:'+row['lookup_scope']+' AND (name:('+terms+') OR aliases:('+terms+'))' if terms else 'lookup_scope:'+row['lookup_scope']
        hits=repository.entity_candidates(scope['company_id'],m['entity_type'],query,row['embedding'],own)
        candidates[m['mention_key']]=[]
        for hit in hits:
            context=window(hit['name'],hit['context'])
            signature=(m['name'],m['context'],hit['name'],context)
            identity=pair_ids.get(signature)
            if identity is None:
                identity=pair_ids[signature]=str(len(pairs))
                pairs.append(dict(id=identity,left=dict(name=m['name'],context=m['context']),
                    right=dict(name=hit['name'],context=context)))
            candidates[m['mention_key']].append(dict(id=identity,key=hit['key']))
            parent.setdefault(hit['key'],hit['key'])
    verdicts={}
    for offset in range(0,len(pairs),16):
        repository.renew_entity_job(scope)
        batch=pairs[offset:offset+16]
        result=request_model(batch)
        if len(result['decisions'])!=len(batch) or {r['id'] for r in result['decisions']}!={p['id'] for p in batch}:
            raise ValueError('Incomplete identity judgments')
        verdicts.update({r['id']:r for r in result['decisions']})

    def root(key):
        while parent[key]!=key:
            parent[key]=parent[parent[key]];key=parent[key]
        return key

    decisions=[];linked=unresolved=0
    for m in mentions:
        hits=candidates[m['mention_key']]
        same=[h for h in hits if verdicts[h['id']].get('status')=='same'
              and valid_score(verdicts[h['id']].get('same'),.9)
              and valid_score(verdicts[h['id']].get('different'),0)
              and verdicts[h['id']].get('same',0)-verdicts[h['id']].get('different',0)>=.1]
        targets={root(h['key']) for h in same}
        own=root(registered[m['mention_key']])
        # More than one competing identity is deliberately left unresolved.
        if len(targets)==1:
            target=targets.pop();parent[max(own,target)]=min(own,target);status='model_linked';linked+=1
        else:
            status='unresolved' if hits else 'separate';unresolved+=bool(hits)
        decisions.append(dict(mention_key=m['mention_key'],status=status,
            candidates=json.dumps([dict(h,**{k:v for k,v in verdicts[h['id']].items() if k!='id'}) for h in hits])))
    grouped={}
    for key in parent:grouped.setdefault(root(key),[]).append(key)
    groups=[sorted(keys) for keys in grouped.values() if len(keys)>1]
    repository.apply_entity_links(scope,groups,decisions)
    return dict(status='complete',mentions=len(mentions),linked=linked,unresolved=unresolved,
        candidate_pairs=sum(map(len,candidates.values())),model_pairs=len(pairs),
        model='knowledgator/gliner-relex-multi-v1.0',
        identity_policy='model_inferred_unreviewed_not_verified',vector_candidate_pool=100)


def enrich_and_sync(run):
    run.structure['knowledge_graph'] = infer_relations(run.structure)
    run.structure['visual_graph'] = dict(status='disabled', provider='none',
        reason='GLiNER is text-only; Qwen image relation inference is disabled', images=[], objects=[], relations=[], text_links=[])
    run.structure['graph_index'] = sync_graph(run,review_structure=True)


def read_context_graph(run, tree, selected, seed_ids=None):
    """Hydrate stored edge identities from current A3 data, never Neo4j text."""
    empty = dict(state='not_indexed', nodes=[], edges=[], partial=False)
    if not getattr(settings, 'A3_GRAPH_ENABLED', False) or tree.get('graph_index', {}).get('status') != 'ready':
        return empty
    try:
        scope = graph_scope(run, tree)
        if tree['graph_index'].get('fingerprint') != scope['fingerprint'] or not visual_sources_fresh(tree):
            return dict(empty, state='stale')
        selected_ids = {leaf['chunk_id'] for leaf in selected}
        if not selected_ids:
            return dict(empty, state='empty')
        stored = repository.context_edges(scope, sorted(selected_ids),
            seed_ids=sorted(selected_ids if seed_ids is None else selected_ids & set(seed_ids)))
        _, nodes, edges = projection(run, tree)
        identity = lambda edge: (edge['from_key'], edge['to_key'], edge['type'],
                                 edge.get('predicate', ''), edge.get('source_leaf_id', ''))
        current_edges = {identity(edge): edge for edge in edges}
        accepted = [current_edges[identity(edge)] for edge in stored['edges'] if identity(edge) in current_edges]
        node_map = {node['key']: node for node in nodes}
        bindings = {node['key']: {node['leaf_id']} & selected_ids for node in nodes if node.get('category') == 'evidence'}
        # Bind headings, table cells and image/object context to actual source
        # leaves. CONTAINS propagates up only; root membership never binds all
        # children to the same paragraph.
        while True:
            changed = False
            for edge in edges:
                a, b, kind = edge['from_key'], edge['to_key'], edge['type']
                pairs = [(a,b)] if kind in {'HAS_EVIDENCE','CONTAINS'} else [(b,a)] if kind in {'MENTIONS','HAS_VISUAL','EXPLAINS','HAS_ROW','HAS_CELL','HAS_EMBEDDING'} else [(a,b)] if kind == 'APPEARS_IN' and node_map[a].get('category') == 'visual_object' else []
                for target, origin in pairs:
                    before = len(bindings.setdefault(target,set()))
                    bindings[target].update(bindings.get(origin,set()))
                    changed |= len(bindings[target]) != before
            if not changed:
                break
        keys = sorted({edge[side] for edge in accepted for side in ('from_key','to_key')
                       if bindings.get(edge[side])} | {key for key,node in node_map.items()
                       if node.get('category')=='evidence' and bindings.get(key)})
        aliases = {key: f'v{run.version_id}:n{i}' for i,key in enumerate(keys,1)}
        result_nodes = []
        for key in keys:
            node = node_map[key]
            item = dict(id=aliases[key], kind=node.get('kind') or node['category'],
                        label=node.get('title') or node.get('name') or node.get('text','') or node.get('source_id') or node['category'],
                        source_leaf_ids=sorted(bindings[key]), origin=node.get('origin','source_structure'))
            if node.get('bbox_json'):
                item['bbox'] = json.loads(node['bbox_json'])
            for field in ('page_number','image_path','reading_stream_id','reading_stream_kind',
                          'reading_stream_status','reading_stream_position','parent_reading_stream_id','reading_document_position'):
                if field in node: item[field] = node[field]
            if node.get('row_index') is not None: item['row'] = node['row_index']
            if node.get('column_index') is not None: item['column'] = node['column_index']
            for field in ('rowspan','colspan'):
                if node.get(field) is not None:item[field]=node[field]
            result_nodes.append(item)
        result_edges = []
        for edge in accepted:
            if edge['from_key'] not in aliases or edge['to_key'] not in aliases:
                continue
            item = dict(from_id=aliases[edge['from_key']], to_id=aliases[edge['to_key']],
                        type=edge['type'], predicate=edge.get('predicate',''),
                        origin=edge.get('origin','source_structure'),
                        review_status=edge.get('review_status','unreviewed' if edge['type'] in ('RELATED','EXPLAINS',*SEMANTIC_EDGE_TYPES) else 'source_extracted'),
                        source_leaf_ids=[edge['source_leaf_id']] if edge.get('source_leaf_id') in selected_ids else [])
            target=edge.get('target_source_leaf_id')
            if target in selected_ids and target not in item['source_leaf_ids']:item['source_leaf_ids'].append(target)
            for field in ('quote','target_quote','confidence','polarity','modality','condition_quotes','scope_quote',
                          'structure_review_status','source_review_status','review_origin','review_evidence_json',
                          'qualification_quote','reading_stream_id','from_char_start','from_char_end','to_char_start','to_char_end'):
                if edge.get(field) or field in {'from_char_start','from_char_end','to_char_start','to_char_end'} and edge.get(field) is not None:
                    item[field] = edge[field]
            result_edges.append(item)
        return dict(state='ready', version_id=run.version_id, run_id=run.pk,
                    retrieved_edges=len(stored['edges']),delivered_edges=len(result_edges),delivered_nodes=len(result_nodes),
                    seed_leaf_ids=sorted(selected_ids if seed_ids is None else selected_ids & set(seed_ids)),
                    context_scope='direct_seed_relations_and_source_paths', nodes=result_nodes, edges=result_edges,
                    omitted_edges=len(stored['edges'])-len(result_edges),
                    partial=stored['truncated'] or len(result_edges)<len(stored['edges']),
                    policy='source_bound_graph_context_not_verified_semantic_truth')
    except Exception as error:
        return dict(empty, state='unavailable', error_type=type(error).__name__)


def expand_graph(run, tree, seeds):
    """Rehydrate current authorized leaves; never trust graph text as evidence."""
    status = tree.get('graph_index', {}).get('status', 'not_indexed')
    if not getattr(settings, 'A3_GRAPH_ENABLED', False) or status != 'ready' or not seeds:
        return tree, dict(state=status, candidates=0)
    try:
        if not visual_sources_fresh(tree):
            return tree, dict(state='stale_visual_source',candidates=0)
        scope = graph_scope(run, tree)
        if tree['graph_index'].get('fingerprint') != scope['fingerprint']:
            return tree, dict(state='stale', candidates=0)
        rows = repository.neighbors(scope, [s['chunk_id'] for s in seeds])
        allowed = {leaf['chunk_id'] for leaf in tree['leaves']}
        seed_ids = {s['chunk_id'] for s in seeds}
        by_seed = {seed:[] for seed in seed_ids}
        for row in rows:
            seed,target = row.get('seed_id'),row.get('leaf_id')
            if seed in by_seed and target in allowed and target not in by_seed[seed]:
                by_seed[seed].append(target)
        related = {target for targets in by_seed.values() for target in targets}
        leaves = [dict(leaf, graph_related_chunk_ids=by_seed[leaf['chunk_id']])
                  if leaf['chunk_id'] in by_seed else leaf for leaf in tree['leaves']]
        return dict(tree, leaves=leaves), dict(state='ready', candidates=len(related),
            seed_neighbors=by_seed, unreviewed_relations_retrieval_only=True)
    except Exception as exc:
        return tree, dict(state='unavailable', candidates=0, error_type=type(exc).__name__)


def valid_bbox(box):
    if not isinstance(box, list) or len(box) != 4:
        raise ValueError('Expected an image-normalized bounding box')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1000 for v in box):
        raise ValueError('Invalid bounding box coordinates')
    if box[0] >= box[2] or box[1] >= box[3]:
        raise ValueError('Empty or reversed bounding box')
    return box


def spatial_relations(objects, near_distance=80):
    """Local, aligned, unobstructed neighbors; never semantic connectivity.

    Coordinates are normalized to 0..1000. Keep one nearest right/below
    neighbor per box, and at most two mutual NEAR neighbors per box.
    """
    if not math.isfinite(near_distance) or not 0 <= near_distance <= 300:
        raise ValueError('Invalid adjacency threshold')
    boxes = [valid_bbox(obj['bbox']) for obj in objects]
    nearest, nearby = {}, {i: [] for i in range(len(objects))}

    def blocked(source, target, corridor):
        return any(k not in (source,target)
                   and min(c[2],corridor[2]) > max(c[0],corridor[0])
                   and min(c[3],corridor[3]) > max(c[1],corridor[1])
                   for k,c in enumerate(boxes))

    def directional(source, target, kind):
        a, b = boxes[source], boxes[target]
        if kind == 'LEFT_OF':
            gap = b[0]-a[2]
            lo, hi = max(a[1],b[1]), min(a[3],b[3])
            overlap = (hi-lo)/min(a[3]-a[1],b[3]-b[1])
            corridor = [a[2],lo,b[0],hi]
        else:
            gap = b[1]-a[3]
            lo, hi = max(a[0],b[0]), min(a[2],b[2])
            overlap = (hi-lo)/min(a[2]-a[0],b[2]-b[0])
            corridor = [lo,a[3],hi,b[1]]
        if not 0 <= gap <= near_distance or overlap < .5:
            return
        # Another block in the shared corridor separates these endpoints.
        if blocked(source,target,corridor):
            return
        rank = (gap, -overlap, str(objects[target]['key']))
        key = (source,kind)
        if key not in nearest or rank < nearest[key][0]:
            nearest[key] = (rank,target)

    for i, a in enumerate(boxes):
        for j in range(i+1,len(boxes)):
            b = boxes[j]
            if a[2] <= b[0]: directional(i,j,'LEFT_OF')
            elif b[2] <= a[0]: directional(j,i,'LEFT_OF')
            if a[3] <= b[1]: directional(i,j,'ABOVE')
            elif b[3] <= a[1]: directional(j,i,'ABOVE')
            dx, dy = max(a[0]-b[2],b[0]-a[2],0), max(a[1]-b[3],b[1]-a[3],0)
            overlaps = min(a[2],b[2])>max(a[0],b[0]) and min(a[3],b[3])>max(a[1],b[1])
            distance = math.hypot(dx,dy)
            if not overlaps and distance <= near_distance:
                x = sorted((min(a[2],b[2]),max(a[0],b[0])))
                y = sorted((min(a[3],b[3]),max(a[1],b[1])))
                if not blocked(i,j,[x[0],y[0],x[1],y[1]]):
                    nearby[i].append((distance,str(objects[j]['key']),j))
                    nearby[j].append((distance,str(objects[i]['key']),i))
    close = {i:{row[2] for row in sorted(rows)[:2]} for i,rows in nearby.items()}
    pairs = [(i,target,kind) for (i,kind),(_,target) in nearest.items()]
    directional_pairs = {frozenset((i,j)) for i,j,_ in pairs}
    pairs.extend((i,j,'NEAR') for i,targets in close.items() for j in targets
                 if str(objects[i]['key']) < str(objects[j]['key']) and i in close[j]
                 and frozenset((i,j)) not in directional_pairs)
    return [dict(from_key=objects[i]['key'],to_key=objects[j]['key'],kind=kind,
                 origin='local_bbox_neighbors_not_semantics',review_status='unreviewed',
                 threshold=near_distance)
            for i,j,kind in sorted(pairs,key=lambda p:(str(objects[p[0]]['key']),str(objects[p[1]]['key']),p[2]))]


def visual_sources_fresh(tree):
    root=Path(settings.MEDIA_ROOT).resolve()
    for image in tree.get('visual_graph',{}).get('images',[]):
        try:
            path=(root/image['image_path']).resolve()
            if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size>20*1024*1024: return False
            if hashlib.sha256(path.read_bytes()).hexdigest()!=image['sha256']: return False
        except (ValueError,OSError): return False
    return True


def append_layout_edges(tree, node, edge):
    pages, spatial_pages, blocks, tables, created, contained = {}, {}, {}, {}, set(), set()
    row_sources = []
    table_sources = {}
    structure_nodes={n['id']:n for n in tree.get('nodes',[])}
    owner_sources={}
    for leaf in tree.get('leaves',[]):
        owner_sources.setdefault(leaf.get('node_id'),set()).add(leaf.get('source_chunk_id') or leaf['chunk_id'])
    def add(identity, **props):
        if identity not in created:
            node(identity, **props); created.add(identity)
    for leaf in tree.get('leaves', []):
        page = leaf.get('page_number', 1)
        image = leaf.get('page_image_path') or leaf.get('image_path')
        if image:
            image_id = 'layout-image:'+hashlib.sha256(image.encode()).hexdigest()
            add(image_id, category='source_image', image_path=image, page_number=page)
            edge('leaf:'+leaf['chunk_id'], image_id, 'HAS_VISUAL', origin='source_image_path')
        source = str(leaf.get('source_chunk_id') or leaf['chunk_id'])
        identity = f'layout-block:{page}:{source}'
        box = leaf.get('bbox') or []
        if identity not in blocks and len(box) == 4 and box[0] < box[2] and box[1] < box[3] and all(0 <= x <= 1000 for x in box):
            source_metadata = leaf.get('structure_metadata') or {}
            blocks[identity] = dict(key=identity, bbox=box,
                                   stream_id=leaf.get('reading_stream_id'),
                                   order_unresolved=source_metadata.get('reading_order_unresolved',False) or leaf.get('reading_stream_status')=='unresolved',
                                   order_source=source_metadata.get('reading_order_source',''),
                                   rank=source_metadata.get('reading_order'))
            add(identity, category='layout_block', kind=leaf.get('layout_type','paragraph'), bbox_json=json.dumps(box), page_number=page, image_path=image or '',
                reading_order=source_metadata.get('reading_order'),
                reading_order_source=source_metadata.get('reading_order_source',''),
                reading_order_scope=source_metadata.get('reading_order_scope','page'),
                reading_order_unresolved=blocks[identity]['order_unresolved'],
                **{k:leaf[k] for k in ('reading_stream_id','reading_stream_kind','reading_stream_status',
                    'reading_stream_position','parent_reading_stream_id','reading_document_position') if k in leaf})
            if image:
                edge(identity, image_id, 'APPEARS_IN', origin='source_page_coordinates')
            # Page reading and reading inside each picture are separate sequences.
            scope = source_metadata.get('reading_order_scope') or source_metadata.get('surya_parent_region_id') or 'page'
            pages.setdefault((page, image or '', leaf.get('reading_stream_id') or scope), []).append(blocks[identity])
            spatial_pages.setdefault((page, image or ''), []).append(blocks[identity])
        if identity in blocks:
            edge(identity, 'leaf:'+leaf['chunk_id'], 'HAS_EVIDENCE', origin='source_block_id')
        metadata = leaf.get('structure_metadata') or {}
        if metadata.get('ocr_status') in {'failed','rejected','empty','unresolved'}:
            continue
        rows = metadata.get('table_rows')
        if not rows and isinstance(metadata.get('table_values'), list):
            rows = [metadata['table_values']]
        if not isinstance(rows, list) or not rows:
            continue
        owner=structure_nodes.get(leaf.get('node_id'),{})
        native_owner=owner.get('kind')=='table' and owner_sources.get(owner['id'])=={source}
        table_id = 'node:'+owner['id'] if native_owner else f'layout-table:{page}:'+str(metadata.get('table_id') or source)
        model_cells = metadata.get('table_header_origin') in {'granite_first_row_unverified','surya_html_unreviewed'}
        cell_origin = 'surya_html' if metadata.get('table_header_origin')=='surya_html_unreviewed' else 'granite_table_values_source_aligned' if model_cells else 'source_table_cells'
        cell_review = 'unreviewed' if model_cells else 'source_extracted'
        if not native_owner:add(table_id, category='table', origin=cell_origin, review_status=cell_review)
        if not native_owner:edge(table_id, 'leaf:'+leaf['chunk_id'], 'HAS_EVIDENCE', origin=cell_origin)
        table_sources.setdefault(table_id, set()).add(leaf['chunk_id'])
        if identity in blocks and (identity, table_id) not in contained:
            contained.add((identity, table_id))
            edge(identity, table_id, 'CONTAINS', origin='source_table_block')
        for i, values in enumerate(rows):
            if not isinstance(values, list):
                continue
            row_index = metadata.get('table_row', i+1) if len(rows)==1 else i+1
            row_id = f'{table_id}:row:{row_index}'
            if row_id in tables:
                continue
            tables[row_id] = True
            add(row_id, category='table_row', row_index=row_index, origin=cell_origin, review_status=cell_review)
            edge(table_id, row_id, 'HAS_ROW', origin=cell_origin, review_status=cell_review)
            row_sources.append((table_id, row_id, leaf['chunk_id']))
            explicit = metadata.get('table_cells')
            cells = [c for c in explicit if c['row']==row_index] if isinstance(explicit,list) else [
                dict(column=col,text=value) for col,value in enumerate(values,1)]
            for cell in cells:
                col, value = cell['column'], cell['text']
                cell_id = f'{row_id}:cell:{col}'
                add(cell_id, category='table_cell', row_index=row_index, column_index=col,
                    rowspan=cell.get('rowspan',1),colspan=cell.get('colspan',1),
                    text=str(value or ''), origin=cell_origin, review_status=cell_review)
                edge(row_id, cell_id, 'HAS_CELL', origin=cell_origin, review_status=cell_review)
    # A one-source table already identifies every row's source. With multiple
    # source fragments retain row bindings to avoid mixing their provenance.
    for table_id, row_id, source_id in row_sources:
        if len(table_sources[table_id]) > 1:
            edge(row_id, 'leaf:'+source_id, 'HAS_EVIDENCE')
    for group in pages.values():
        native = any(b['order_source'] in {'surya_layout_model','surya_full_page_model'} for b in group)
        if native:
            ranks = [b['rank'] for b in group]
            valid = all(type(rank) is int and rank >= 0 for rank in ranks)
            if (not valid or len(set(ranks)) != len(ranks)
                    or any(b['order_unresolved'] for b in group)):
                continue
            group = sorted(group,key=lambda b:b['rank'])
        # The chosen source/model stream is separate from spatial relations.
        # Ambiguous order must not produce NEXT edges.
        for a,b in zip(group, group[1:]):
            if a['order_unresolved'] or b['order_unresolved']:
                continue
            provider = a['order_source'] if a['order_source'] == b['order_source'] and a['order_source'] else 'observed_source_order'
            edge(a['key'], b['key'], 'NEXT', origin=provider,reading_stream_id=a.get('stream_id'))
    for group in spatial_pages.values():
        for relation in spatial_relations(group):
            edge(relation['from_key'], relation['to_key'], relation['kind'],
                 origin='source_bbox_geometry_not_semantics', threshold=relation.get('threshold'))


