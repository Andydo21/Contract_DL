"""Generate an A2 answer from authorized retrieved knowledge, with evidence checks."""
from ai_extract.services.contract_pipeline_service import request_qwen, retrieval_gate, validate_answer, render_cited_claims, QwenGatewayError, QwenContextLimitError, QwenIncompleteAnswerError
from shared.retrieval import source_excerpt
from .search_evidence_service import EXPERT_INSTRUCTION
import json
import re
from ai_extract import SEMANTIC_EDGE_TYPES


def distinct_document_passages(sources):
    """Avoid separately citing a sentence already inside a fuller same-context source."""
    from ai_extract.services.document_structure_service import table_context
    def context(source):
        return (source.get('version_id'), source.get('page_number'),
                tuple(source.get('heading_path', [])),
                json.dumps(table_context(source), sort_keys=True, ensure_ascii=False))
    texts = [re.sub(r'\s+', ' ', source.get('text', '')).strip() for source in sources]
    return [source for i, source in enumerate(sources) if not (
        source.get('version_id') and texts[i] and any(
            len(texts[i]) < len(texts[j]) and texts[i] in texts[j]
            and context(source) == context(other)
            for j, other in enumerate(sources)))]


def generation_coverage(coverage):
    """Send scope limits to Qwen, keeping verbose runtime diagnostics in the UI."""
    keys = ('mode', 'access_scope', 'partial', 'indexed_only', 'versions_total',
            'versions_scanned', 'versions_deeply_searched', 'latest_versions_only',
            'whole_contract_review', 'omitted_expansions', 'external_web_search', 'requested_parts', 'answer_parts')
    compact = {key: coverage[key] for key in keys if key in coverage}
    details = [coverage] + [item.get('coverage', {}) for item in coverage.get('version_details', [])]
    for key in ('unresolved_article_references', 'unresolved_document_references'):
        compact[key] = list(dict.fromkeys(ref for detail in details for ref in detail.get(key, [])))
    compact['whole_contract_review'] = coverage.get('whole_contract_review', False)
    return compact


def graph_source_order(contexts, evidence):
    """Present sources in stored NEXT order where both bindings are unambiguous."""
    import heapq
    # An abstention does not refute native layout. Retain it as a provisional
    # presentation order, while refusing explicit model-disputed constraints.
    uncertain={'model_disputed'}
    contested=any(e.get('type')=='NEXT' and e.get('review_status') in uncertain
                  for c in contexts for e in c.get('edges',[]))
    if evidence and not contested and all(type(s.get('reading_document_position')) is int
                        and s.get('reading_stream_status') in {'model_predicted','source_order'} for s in evidence):
        versions={identity:i for i,identity in enumerate(dict.fromkeys(s.get('version_id') for s in evidence))}
        return sorted(evidence,key=lambda s:(versions[s.get('version_id')],s['reading_document_position']))
    by_leaf = {(source.get('version_id'),source.get('chunk_id')):i for i,source in enumerate(evidence)}
    following = [set() for _ in evidence]
    incoming = [0] * len(evidence)
    for context in contexts:
        if context.get('state') != 'ready':
            continue
        nodes = {node['id']:{by_leaf[(context.get('version_id'),leaf)]
                    for leaf in node.get('source_leaf_ids',[]) if (context.get('version_id'),leaf) in by_leaf}
                 for node in context.get('nodes',[])}
        for edge in context.get('edges',[]):
            a,b = nodes.get(edge.get('from_id'),set()),nodes.get(edge.get('to_id'),set())
            if edge.get('type')=='NEXT' and edge.get('review_status') not in uncertain and len(a)==len(b)==1:
                start,end = next(iter(a)),next(iter(b))
                if start!=end and end not in following[start]:
                    following[start].add(end)
                    incoming[end] += 1
    ready = [i for i,count in enumerate(incoming) if not count]
    heapq.heapify(ready)
    ordered = []
    while ready:
        index = heapq.heappop(ready)
        ordered.append(evidence[index])
        for end in sorted(following[index]):
            incoming[end] -= 1
            if not incoming[end]:
                heapq.heappush(ready,end)
    return ordered if len(ordered)==len(evidence) else evidence



def focus_answer_sources(payload, parts, previous_claims=()):
    """Limit a repair to its ranked sources and direct semantic dependencies."""
    wanted={identity for part in parts for identity in part.get('source_ids',[])}
    part_ids={part['id'] for part in parts}
    wanted.update(identity for claim in previous_claims if part_ids.intersection(claim.get('part_ids',[]))
                  for identity in claim.get('evidence_ids',[]))
    if not wanted:return payload
    graph=payload.get('graph_context') or {}
    nodes={node['id']:node for node in graph.get('nodes',[])}
    seeds=set(wanted)
    for edge in graph.get('edges',[]):
        if edge.get('type') not in set(SEMANTIC_EDGE_TYPES)|{'HAS_CAPTION'}:continue
        a=nodes.get(edge.get('from_id'),{}).get('evidence_ids',[])
        b=nodes.get(edge.get('to_id'),{}).get('evidence_ids',[])
        if seeds.intersection(a):wanted.update(b)
        if seeds.intersection(b):wanted.update(a)
    focused,sources=claim_verification_context(graph,payload['evidence'],[dict(evidence_ids=sorted(wanted))])
    if not sources:return payload
    return dict(payload,evidence=sources,graph_context=focused)

def request_answer_with_context_retry(request_model, payload):
    """Retry shorter output, then read smaller source-bound batches as needed.

    Reducing output cannot fit a prompt larger than the entire context. In that
    case split passages, never truncate them or substitute fabricated answers.
    Citation checks and advisory self-review run on the merged claims.
    """
    try:
        return request_model('contract_qa',payload)
    except QwenContextLimitError as error:
        overflow = error
        retry=dict(payload,answer_detail='concise',
            max_output_tokens=max(64,min(2048,error.output_tokens//2)))
        if not getattr(error, 'preflight', False):
            try:
                return request_model('contract_qa',retry)
            except QwenContextLimitError as second_error:
                overflow = second_error
        sources=retry['evidence']
        if len(sources)<2:
            raise overflow
    responses=[];processed=[]
    required={p['id'] for p in retry.get('answer_parts',[])}
    middle=len(sources)//2
    for batch in (sources[:middle],sources[middle:]):
        graph,_=claim_verification_context(retry.get('graph_context') or {},sources,
            [dict(evidence_ids=[s['evidence_id'] for s in batch])])
        child=dict(retry,evidence=batch,graph_context=dict(graph,partial=True),
            source_packets=answer_source_packets(batch,retry.get('answer_parts',[]),graph),
            coverage=dict(retry.get('coverage',{}),partial=True),
            instruction=retry.get('instruction','')+(
                ' This is one source batch of a larger retrieval. Return only claims supported by this batch. '
                'Do not claim that information is absent from the whole document or other batches. '
                'Leave parts unsupported by this batch unanswered; other batches will be read separately.'))
        covered={part for r in responses for c in r.get('citation_claims',[]) for part in c.get('part_ids',[])}
        if required:
            pending=[part for part in retry['answer_parts'] if part['id'] not in covered]
            if not pending:break
            child=dict(child,answer_parts=pending,coverage=dict(child['coverage'],requested_parts=[p['question'] for p in pending]))
        response=request_answer_with_context_retry(request_model,child)
        # Review the merged answer once. A model verdict must not silently
        # remove paragraphs here or add another call for every source batch.
        responses.append(response)
        processed.extend(s['evidence_id'] for s in batch)
        covered={part for r in responses for c in r.get('citation_claims',[]) for part in c.get('part_ids',[])}
        # Once the model has addressed all parts, review the merged answer.
        # Do not generate more competing answers from lower-priority batches.
        if required and required<=covered:break
    claims=[]
    for response in responses:
        for claim in response.get('citation_claims',[]):
            if claim not in claims:claims.append(claim)
    combined=dict(claims=claims)
    answer=render_cited_claims(combined,sources) if claims else ''
    claims=combined['claims']
    return dict(answer=answer,
        citation_claims=claims,insufficient_evidence=not claims,
        answer_part_coverage=[dict(part,status='answered' if any(part['id'] in c.get('part_ids',[]) for c in claims) else 'unavailable') for part in retry.get('answer_parts',[])],
        citation_analysis=[item for r in responses for item in r.get('citation_analysis',[])],
        answer_notes=[item for r in responses for item in r.get('answer_notes',[])],
        qwen_outputs=[item for r in responses for item in r.get('qwen_outputs',[])],
        generation_input=dict(evidence_ids=[s['evidence_id'] for s in sources],
            context_retry='shorter_output_then_source_batches',requested_output_tokens=retry['max_output_tokens'],
            processed_source_ids=processed,unread_source_ids=[s['evidence_id'] for s in sources if s['evidence_id'] not in processed],
            batches=[r.get('generation_input',{}) for r in responses]))


def answer_source_packets(sources, parts, graph):
    """Share source scopes once; question facets are requests, never source facts."""
    scopes=[];by_scope={};source_scope={}
    nodes={n['id']:n for n in graph.get('nodes',[])}
    owners={}
    for edge in graph.get('edges',[]):
        owner=nodes.get(edge.get('from_id'),{})
        if not owner or edge.get('type')!='HAS_EVIDENCE' or owner.get('kind') in {'document','page','evidence'}:continue
        for identity in nodes.get(edge.get('to_id'),{}).get('evidence_ids',[]):
            owners.setdefault(identity,[]).append(owner['id'])
    for source in sources:
        fields={k:source[k] for k in ('document_id','version_id','original_name','heading_path',
            'reading_stream_id','reading_stream_kind','parent_reading_stream_id') if source.get(k) is not None}
        if owners.get(source['evidence_id']):fields['owner_node_ids']=owners[source['evidence_id']]
        # Missing structural ownership must not group all blocks on one page.
        if not fields.get('heading_path') and not fields.get('reading_stream_id'):
            fields['unresolved_source_scope']=source.get('chunk_id',source['evidence_id'])
        identity=json.dumps(fields,sort_keys=True,ensure_ascii=False)
        if identity not in by_scope:
            by_scope[identity]=len(scopes)
            scopes.append(dict(id=f'S{len(scopes)+1}',scope=fields,source_ids=[]))
        scope=scopes[by_scope[identity]]
        scope['source_ids'].append(source['evidence_id'])
        source_scope[source['evidence_id']]=scope['id']
    packets=[]
    available=set(source_scope)
    for part in parts:
        direct=[identity for identity in part.get('source_ids',[]) if identity in available]
        focused=focus_answer_sources(dict(evidence=sources,graph_context=graph),[dict(part,source_ids=direct)]) if direct else {}
        related=[s['evidence_id'] for s in focused.get('evidence',[]) if s['evidence_id'] not in direct]
        packets.append(dict(part_id=part['id'],query_scope=part.get('query_scope',{}),
            direct_source_ids=direct,related_source_ids=related,
            scope_ids=list(dict.fromkeys(source_scope[i] for i in [*direct,*related]))))
    documents=[];contexts=[]
    def reference(records,fields,prefix):
        for record in records:
            if record['fields']==fields:return record['id']
        identity=f'{prefix}{len(records)+1}'
        records.append(dict(id=identity,fields=fields))
        return identity
    compact=[]
    for scope in scopes:
        fields=scope['scope']
        document={k:fields[k] for k in ('document_id','version_id','original_name') if k in fields}
        context={k:fields[k] for k in ('heading_path','reading_stream_id','reading_stream_kind','parent_reading_stream_id') if k in fields}
        item=dict(id=scope['id'],document_ref=reference(documents,document,'D'),
            context_ref=reference(contexts,context,'C'),source_ids=scope['source_ids'])
        if fields.get('owner_node_ids'):item['owner_node_ids']=fields['owner_node_ids']
        if 'unresolved_source_scope' in fields:item['scope_unknown']=True
        compact.append(item)
    return dict(parts=packets,documents=documents,contexts=contexts,source_scopes=compact)


def generate_checked_answer(payload, request_model=None, progress=None):
    """One generation with inline caveats; validate source bindings without a judge call."""
    model=request_model or request_qwen
    evidence=[s for s in payload['evidence'] if s.get('text','').strip()
              or payload.get('use_images') and s.get('image_path')]
    coverage=payload.get('coverage',{})
    contexts=[coverage.get('graph_context',{})]+coverage.get('graph_contexts',[])+[
        item.get('coverage',{}).get('graph_context',{}) for item in coverage.get('version_details',[])]
    evidence=graph_source_order(contexts,evidence)
    graph=payload.get('graph_context')
    if graph is None:graph=bind_graph_context(contexts,evidence,query=payload.get('query',''))
    planned=coverage.get('answer_parts') or [dict(question=q) for q in dict.fromkeys(coverage.get('requested_parts',[]))]
    parts=[dict(p,id=f'P{i}') for i,p in enumerate(planned,1)]
    for ordinal,part in enumerate(parts,1):
        ranked=[]
        for source in evidence:
            ranks=[h['rank'] for h in source.get('retrieval_hints',[])
                   if h.get('part')==ordinal and type(h.get('rank')) is int]
            if ranks:ranked.append((min(ranks),source['evidence_id']))
        if ranked:part['source_ids']=[identity for _,identity in sorted(ranked)]
    payload=dict(payload,evidence=evidence,coverage=generation_coverage(coverage),graph_context=graph,
        answer_parts=parts,source_packets=answer_source_packets(evidence,parts,graph),
        answer_format='cited_claims',answer_detail=payload.get('answer_detail','explanatory'),
        analyze_citations=False,check_completeness=True,inline_review=True)
    result=dict(answer=source_excerpt(evidence),answer_text='Chưa tổng hợp được; bạn có thể đối chiếu các đoạn nguồn bên dưới.',
        generation_status='source_excerpt',citation_check=dict(valid=False),generation_calls=[],qwen_outputs=[],
        generation_diagnostics=dict(state='requested'))
    try:
        # Only malformed citations or an empty answer get one format recovery.
        # Semantic uncertainty never starts a judge/regeneration loop.
        feedback=''
        for attempt in range(2):
            stage='citation_repair' if attempt else 'answer'
            if progress:progress('repairing_citations' if attempt else 'generating')
            sent=dict(payload,repair_feedback=feedback)
            if attempt:sent['previous_answer']=response.get('answer','')
            response=request_answer_with_context_retry(model,sent)
            result['qwen_outputs'].extend(dict(item,stage=stage) for item in response.get('qwen_outputs',[]))
            result['generation_calls'].append(dict(response.get('generation_input',
                dict(evidence_ids=[s['evidence_id'] for s in evidence])),stage=stage))
            answer=response['answer']
            if response.get('insufficient_evidence'):
                if not attempt and evidence:
                    feedback='Re-examine the supplied passages and table headers. Answer supported parts and state the remaining gaps, without inventing facts.'
                    continue
                result.update(answer=answer,answer_text=answer,generation_status='abstained',
                    generation_diagnostics=dict(state='insufficient_evidence'))
                return result
            check=validate_answer(answer,evidence)
            if check['valid']:break
            feedback='Repair source IDs/citation format only: '+', '.join(check.get('failures',[]))
        result['citation_check']=check
        if not check['valid']:
            result['generation_diagnostics']=dict(state='citation_validation_failed',failures=check.get('failures',[]))
            return result
        claims=response.get('citation_claims',[])
        notes=response.get('answer_notes',[])
        diagnostics=dict(state='generated',self_review='inline_model_uncertainty_not_verified')
        missing=[p['question'] for p in response.get('answer_part_coverage',[]) if p.get('status')!='answered']
        if missing:diagnostics['completeness_warning']=dict(complete=False,missing_parts=missing)
        if notes:diagnostics['review_warning']=dict(reason='\n'.join(n['text'] for n in notes),
            claim_checks=[],unavailable=False,scope='inline_model_uncertainty_not_proof_of_truth')
        result.update(answer=answer,answer_text='\n\n'.join(c['text'].strip() for c in claims) if claims
            else re.sub(r'\s*\[E\d+\]','',answer),generation_status='generated',generation_diagnostics=diagnostics,
            answer_notes=notes,citation_analysis=response.get('citation_analysis',[]),
            answer_source_ids=list(dict.fromkeys(identity for c in claims for identity in c['evidence_ids'])),
            answer_part_coverage=response.get('answer_part_coverage',[]))
    except (QwenGatewayError,KeyError,TypeError) as error:
        result['qwen_outputs'].extend(dict(item,stage='failed') for item in getattr(error,'qwen_outputs',[]))
        state='gateway_unavailable'
        if isinstance(error,QwenIncompleteAnswerError):state='output_limit_reached'
        elif isinstance(error,QwenContextLimitError):state='context_limit_exceeded'
        elif getattr(error,'qwen_outputs',[]):state='response_rejected'
        result['generation_diagnostics']=dict(state=state,error_type=type(error).__name__,reason=str(error)[:500])
        if isinstance(error,QwenContextLimitError):result['generation_diagnostics'].update(
            context_capacity=error.capacity,prompt_tokens=error.prompt_tokens,requested_output_tokens=error.output_tokens)
    return result


def eligible_answer_sources(query, citations):
    """Apply the same provenance policy before seed admission and generation."""
    asks_expert = bool(re.search(r'chuyên gia|kinh nghiệm|khuyến nghị|expert|advice|demo',query,re.I))
    # Synthetic sample advice is available in the UI but does not add factual
    # evidence to ordinary document questions. Genuine approved advice stays.
    return [c for c in citations if not c.get('is_demo') or asks_expert]


def answer_from_sources(query, citations, coverage, progress=None):
    eligible = eligible_answer_sources(query,citations)
    # Retrieval already selected relevant, source-bound chunks and expansions.
    # Do not cut away their conditions again for generation.
    evidence = [dict(c, text=c.get('text', '')) for c in distinct_document_passages(eligible)]
    prompt_coverage = generation_coverage(coverage)
    quality = retrieval_gate(query, evidence, dict(coverage, **prompt_coverage))
    result = dict(answer=source_excerpt(evidence) if evidence else 'Chưa tìm thấy bằng chứng trong kho tài liệu đã trích xuất.',
                  generation_status='source_excerpt' if evidence else 'abstained',
                  generation_diagnostics={'state': 'insufficient_evidence'}, quality_gate=quality,
                  citation_check={'valid': False}, generation_calls=[])
    if not evidence:
        return result
    if all(c.get('evidence_kind') == 'expert_question' for c in evidence):
        result.update(answer='Chỉ tìm thấy câu hỏi đã lưu, chưa có câu trả lời hoặc bằng chứng để kết luận.',
                      generation_status='abstained')
        return result
    payload = dict(query=query, evidence=evidence, coverage=prompt_coverage,
                   answer_format='cited_claims',
                   answer_detail='explanatory',
                   use_images=needs_source_images(query,evidence),
                   instruction='Answer each requested part with the relevant source-supported explanation and conditions. Keep documents, versions and subjects distinct; describe disagreements rather than merging them into one assertion. Use the graph internally to interpret the sources; keep retrieval details out of the answer.')
    if any(c.get('evidence_kind') in {'expert_opinion','expert_question','expert_unit'} for c in evidence):
        payload['expert_policy']=EXPERT_INSTRUCTION
    graph_contexts = [coverage.get('graph_context', {})] + coverage.get('graph_contexts', []) + [item.get('coverage', {}).get('graph_context', {}) for item in coverage.get('version_details', [])]
    result['graph_context'] = payload['graph_context'] = bind_graph_context(graph_contexts, evidence, query=query)
    if not quality['accepted']:
        result.update(answer='Chưa tìm thấy bằng chứng đủ liên quan để trả lời câu hỏi trong kho tài liệu được phép truy cập. Bạn có thể xem các ứng viên ở phần nguồn bên dưới.',
                      generation_status='abstained')
        return result
    result.update(generate_checked_answer(payload, progress=progress))
    return result


def needs_source_images(query, evidence):
    """Use page images for visual questions or primary hits without readable text."""
    visual = re.search(r'\b(?:ảnh|hình|sơ đồ|bản vẽ|biểu đồ|diagram|drawing|figure|image|chart|cad|bbox)\b', query, re.I)
    matches = [source for source in evidence if source.get('evidence_kind')!='expert_opinion'
               and source.get('expansion_reason','query_match')=='query_match']
    return bool(visual or matches and not any(source.get('text','').strip() for source in matches)
                and any(source.get('image_path') for source in matches))

def bind_graph_context(contexts, evidence, max_chars=None, query=''):
    """Send only graph endpoints bound to evidence actually delivered to Qwen."""
    import json
    by_leaf = {}
    for source in evidence:
        if source.get('evidence_kind') != 'expert_opinion':
            by_leaf.setdefault((source.get('version_id'), source.get('chunk_id')), []).append(source['evidence_id'])
    result = dict(nodes=[], edges=[], partial=False, omitted_edges=0, filtered_spatial_edges=0,
                  scope='source_bound_subgraph',unavailable_contexts=[],
                  spatial_policy='limited_supplement_not_reading_order_or_semantic_support',
                  policy='graph_navigation_not_independent_factual_evidence')
    meanings = {
        'CONTAINS':'Structural parent to child; not reading order.',
        'HAS_EVIDENCE':'Node to its source evidence; read the passage to establish facts.',
        'APPEARS_IN':'Element to the page where it occurs.',
        'NEXT':'Order within one reading stream only; not semantic continuation. Child-region streams and supplementary streams are separate.',
        'HAS_VISUAL':'Link to the source visual region.',
        'HAS_EMBEDDING':'Link to the retrieval index representation; not a factual assertion.',
        'MENTIONS':'Source passage mentions the entity; not a predicate between entities.',
        'HAS_ROW':'Table to a source row.', 'HAS_CELL':'Row or table to a source cell.',
        'HAS_CAPTION':'Visual element to its caption; respect candidate/review status.',
        'REFERENCES':'Source points to the target; respect the recorded evidence and review status.',
        'DEFINES':'Source proposes a definition of the target.',
        'OBLIGATES':'Proposed obligation; preserve its subject, polarity, modality and conditions.',
        'DEPENDS_ON':'Proposed dependency from source to target.',
        'PART_OF':'Proposed part-to-whole relationship.',
        'DESCRIBES':'Source proposes a description of the target.',
        'EXPLAINS':'Source proposes an explanation of the visual target; verify its cited passage.',
        'APPLIES_TO':'Proposed applicability to the target, subject to recorded conditions.',
        'HAS_AMOUNT':'Proposed amount; retain source unit, currency and conditions.',
        'HAS_DEADLINE':'Proposed deadline; retain source timing and conditions.',
        'PAYS_TO':'Proposed payment direction from payer to payee.',
        'RELATED':'Unspecified association; does not establish a specific predicate.',
        'LEFT_OF':'Left-to-right spatial position only; not ownership or reading order.',
        'ABOVE':'Vertical spatial position only; not ownership or reading order.',
        'NEAR':'Spatial proximity only; does not prove the elements describe each other.',
    }
    present, pending, primary, aliases = {}, [], [], {}
    # Smaller values admit edges earlier; this is not a factual-confidence score.
    priorities = {
        'HAS_EVIDENCE':0, 'HAS_ROW':0, 'HAS_CELL':0,
        'REFERENCES':1, 'DEFINES':1, 'OBLIGATES':1, 'DEPENDS_ON':1,
        'PART_OF':1, 'DESCRIBES':1, 'EXPLAINS':1, 'APPLIES_TO':1,
        'HAS_AMOUNT':1, 'HAS_DEADLINE':1, 'PAYS_TO':1,
        'CONTAINS':2, 'HAS_CAPTION':2, 'NEXT':3,
        'MENTIONS':4, 'HAS_VISUAL':5, 'APPEARS_IN':5, 'RELATED':6,
        'LEFT_OF':8, 'ABOVE':8, 'NEAR':8, 'HAS_EMBEDDING':9,
    }
    def append(item, nodes, budget, count_omitted=True):
        endpoints = [item['from_id'],item['to_id']]
        added = [nodes[key] for key in dict.fromkeys(endpoints) if key not in present]
        candidate = dict(result,nodes=result['nodes']+added,edges=result['edges']+[item])
        candidate['relation_legend'] = {edge['type']:meanings.get(edge['type'], 'Stored relationship; inspect its predicate and source.') for edge in candidate['edges']}
        if budget is not None and len(json.dumps(candidate,ensure_ascii=False)) > budget:
            if count_omitted:result['omitted_edges'] += 1
            return False
        result['nodes'].extend(added)
        present.update({node['id']:node for node in added})
        result['edges'].append(item)
        result['relation_legend'] = candidate['relation_legend']
        return True
    for context in contexts:
        if context.get('state') != 'ready':
            if context.get('state'):
                result['partial']=True
                result['unavailable_contexts'].append({key:context[key] for key in ('state','version_id','run_id') if key in context})
            continue
        result['partial'] |= context.get('partial', False)
        result['omitted_edges'] += context.get('omitted_edges',0)
        nodes = {}
        for node in context.get('nodes', []):
            identifiers = sorted({identifier for leaf in node.get('source_leaf_ids', [])
                for identifier in by_leaf.get((context.get('version_id'),leaf), [])})
            if not identifiers:
                continue
            item = {key:node[key] for key in ('id','kind','label','bbox','page_number','image_path','row','column','rowspan','colspan',
                'reading_stream_id','reading_stream_kind','reading_stream_status','reading_stream_position',
                'parent_reading_stream_id','reading_document_position') if key in node}
            # Prompt-local aliases preserve the actual graph topology without
            # spending the context window repeating opaque database IDs.
            key = (context.get('version_id'), node['id'])
            item['id'] = aliases.setdefault(key, len(aliases)+1)
            if node.get('kind')=='evidence':
                item['label']=' '.join(f'[{identifier}]' for identifier in identifiers)
            item['evidence_ids'] = identifiers
            nodes[node['id']] = item
        if max_chars is None:
            for item in nodes.values():
                if item.get('kind')=='evidence' and item['id'] not in present:
                    result['nodes'].append(item)
                    present[item['id']]=item
        for edge in sorted(context.get('edges', []),key=lambda e:priorities.get(e.get('type'),4)):
            endpoints = [edge.get('from_id'),edge.get('to_id')]
            if any(key not in nodes for key in endpoints):
                result['omitted_edges'] += 1
                continue
            own_ids = sorted({identifier for leaf in edge.get('source_leaf_ids', [])
                for identifier in by_leaf.get((context.get('version_id'),leaf), [])})
            if edge.get('source_leaf_ids') and not own_ids:
                result['omitted_edges'] += 1
                continue
            item = {key:edge[key] for key in ('from_id','to_id','type','predicate','origin','quote','polarity',
                    'modality','condition_quotes','scope_quote','qualification_quote','target_quote','confidence',
                    'reading_stream_id','from_char_start','from_char_end','to_char_start','to_char_end')
                    if edge.get(key) or key in {'from_char_start','from_char_end','to_char_start','to_char_end'} and edge.get(key) is not None}
            if edge.get('review_status'):
                item['review_status']=edge['review_status']
            if edge.get('type') == 'NEXT':
                item['meaning'] = 'reading_order_only_not_same_paragraph_or_semantic_relation'
                item['role'] = 'reading_order'
            elif edge.get('type') in {'LEFT_OF','ABOVE','NEAR'}:
                item.update(role='supplementary',meaning='bbox_position_only_not_reading_order_ownership_or_explanation')
            elif edge.get('origin')=='surya_heading_sequence':
                item.update(role='candidate',meaning='possible_section_scope_from_model_order_not_verified_ownership')
            elif edge.get('predicate')=='caption_candidate':
                item.update(role='candidate',meaning='possible_caption_not_verified_visual_description')
            else:
                item['role'] = 'primary'
            endpoint_sources = [set(nodes[key]['evidence_ids']) for key in endpoints]
            # A shared page/parent can bind many leaves. Its other leaves are
            # not sources for this particular edge to a specific child.
            item['evidence_ids'] = own_ids or sorted(set.intersection(*endpoint_sources)
                or set.union(*endpoint_sources))
            item['from_id'], item['to_id'] = [nodes[key]['id'] for key in endpoints]
            compact_nodes = {node['id']:{k:v for k,v in node.items() if k not in {'bbox','image_path'}}
                             for node in nodes.values()}
            if item.get('role')=='supplementary': pending.append((item,compact_nodes))
            else: primary.append((7 if item.get('role')=='candidate' else priorities.get(item['type'],4),item,compact_nodes))
    # Reserve a small allowance only when valid supplementary geometry exists.
    # Across documents, hierarchy/table/source bindings get the first slots.
    primary_budget = max_chars*85//100 if pending and max_chars is not None else max_chars
    # Direct source-backed semantic links must not be crowded out by a long
    # heading tree. Reserve up to one third, then fill the remaining budget.
    admitted=set()
    for _,item,nodes in primary:
        if item['type'] in SEMANTIC_EDGE_TYPES and append(item,nodes,primary_budget//3 if primary_budget is not None else None,count_omitted=False):
            admitted.add(id(item))
    # Give every available primary relation type a turn before filling the
    # remaining graph budget. Unknown types are preserved, never remapped.
    kinds = sorted({item['type'] for _,item,_ in primary}, key=lambda kind: (priorities.get(kind,4),kind))
    for relation in kinds:
        for _,item,nodes in primary:
            if item['type']==relation and id(item) not in admitted:
                if append(item,nodes,primary_budget,count_omitted=False):
                    admitted.add(id(item))
                    break
    for _,item,nodes in sorted(primary,key=lambda row:row[0]):
        if id(item) not in admitted:append(item,nodes,primary_budget)
    # Across ALL documents, primary edges are admitted before geometry. The
    # supplemental additions may use at most 20% of the total graph budget.
    spatial_budget = (min(max_chars,len(json.dumps(result,ensure_ascii=False))+max_chars//5)
                      if max_chars is not None else None)
    for item,nodes in pending:
        if not append(item,nodes,spatial_budget):
            result['filtered_spatial_edges'] += 1
    result['partial'] |= bool(result['omitted_edges'])
    return result


def _prompt_graph_tables(graph):
    """Fold isolated row/cell branches into grids; keep externally referenced cells explicit."""
    nodes={node['id']:node for node in graph.get('nodes',[])}
    edges=graph.get('edges',[])
    removed=set();grids=[]
    def common(records,exclude):
        return {k:v for k,v in records[0].items() if k not in exclude
                and all(k in row and row[k]==v for row in records)} if records else {}
    for table in nodes.values():
        if table.get('kind')!='table':continue
        row_edges=[e for e in edges if e['type']=='HAS_ROW' and e['from_id']==table['id']]
        row_ids={e['to_id'] for e in row_edges}
        cell_edges=[e for e in edges if e['type']=='HAS_CELL' and e['from_id'] in row_ids]
        cell_ids={e['to_id'] for e in cell_edges}
        internal=row_ids|cell_ids
        if not row_ids or not cell_ids or internal & removed or not internal<=nodes.keys():continue
        branch=row_edges+cell_edges
        # Folding must never erase a reference, semantic proposal or extra parent.
        if any(e not in branch for e in edges if e['from_id'] in internal or e['to_id'] in internal):continue
        if len(row_edges)!=len(row_ids) or len(cell_edges)!=len(cell_ids):continue
        rows=[nodes[i] for i in row_ids];cells=[nodes[i] for i in cell_ids]
        if any(n.get('kind')!='table_row' or set(n)-{'id','kind','label','row','evidence_ids'} for n in rows):continue
        if any(n.get('kind')!='table_cell' or set(n)-{'id','kind','label','row','column','rowspan','colspan','evidence_ids'} for n in cells):continue
        if any(type(n.get('row')) is not int for n in rows+cells):continue
        if len({n['row'] for n in rows})!=len(rows):continue
        if any(type(n.get('column')) is not int for n in cells):continue
        row_defaults=common(rows,{'id','row'})
        cell_defaults=common(cells,{'id','row','column','label','rowspan','colspan'})
        if any(set(n)-{'id','row'}!=set(row_defaults) for n in rows):continue
        if any(set(n)-{'id','row','column','label','rowspan','colspan'}!=set(cell_defaults) for n in cells):continue
        row_relation=common(row_edges,{'from_id','to_id','type'})
        cell_relation=common(cell_edges,{'from_id','to_id','type'})
        if any(set(e)-{'from_id','to_id','type'}!=set(row_relation) for e in row_edges):continue
        if any(set(e)-{'from_id','to_id','type'}!=set(cell_relation) for e in cell_edges):continue
        cell_owner={e['to_id']:e['from_id'] for e in cell_edges}
        if any(nodes[cell_owner[c['id']]]['row']!=c['row'] for c in cells):continue
        grid=[]
        for row in sorted(rows,key=lambda n:n['row']):
            entries=[]
            for cell in sorted((c for c in cells if cell_owner[c['id']]==row['id']),key=lambda n:n['column']):
                spans=[cell.get('rowspan',1),cell.get('colspan',1)]
                entries.append([cell['column'],cell.get('label','')]+(spans if spans!=[1,1] else []))
            grid.append([row['row'],entries])
        grids.append(dict(table_id=table['id'],row_defaults=row_defaults,cell_defaults=cell_defaults,
                          HAS_ROW=row_relation,HAS_CELL=cell_relation,rows=grid))
        removed.update(internal)
    return dict(graph,nodes=[n for n in nodes.values() if n['id'] not in removed],
                edges=[e for e in edges if e['from_id'] not in removed and e['to_id'] not in removed]),grids


def claim_verification_context(graph, sources, claims):
    """Scope a review to cited sources, without traversing shared page hubs."""
    selected={identity for claim in claims for identity in claim.get('evidence_ids',[])}
    passages=[source for source in sources if source['evidence_id'] in selected]
    nodes={node['id']:node for node in graph.get('nodes',[])}
    if not any(item.get('evidence_ids') for item in [*nodes.values(),*graph.get('edges',[])]):
        return graph,passages  # Legacy contexts without bindings cannot be safely narrowed.
    edges=[]
    for edge in graph.get('edges',[]):
        bindings=set(edge.get('evidence_ids',[])) or {
            identity for key in ('from_id','to_id')
            for identity in nodes.get(edge.get(key),{}).get('evidence_ids',[])}
        if not bindings or bindings.intersection(selected):edges.append(edge)
    keep={key for edge in edges for key in (edge['from_id'],edge['to_id'])}
    keep.update(node['id'] for node in nodes.values() if node.get('kind')=='evidence'
                and selected.intersection(node.get('evidence_ids',[])))
    kinds={edge['type'] for edge in edges}
    focused=dict(graph,nodes=[node for key,node in nodes.items() if key in keep],edges=edges,
        relation_legend={k:v for k,v in graph.get('relation_legend',{}).items() if k in kinds},
        verification_scope=dict(source_ids=sorted(selected),
            original_nodes=len(nodes),original_edges=len(graph.get('edges',[]))))
    return focused,passages



def _share_graph_values(graph):
    """Factor repeated metadata, preserving every node, relation and field value."""
    from collections import Counter
    counts = Counter()
    values = {}
    def signature(value):
        if isinstance(value,str) or isinstance(value,list) and value and all(isinstance(v,(str,int,float,bool,type(None))) for v in value):
            encoded=json.dumps(value,ensure_ascii=False,separators=(',',':'))
            return encoded if len(encoded)>=32 else None
    def visit(value):
        key=signature(value)
        if key:
            counts[key]+=1
            values[key]=value
        elif isinstance(value,dict):
            for item in value.values():visit(item)
        elif isinstance(value,list):
            for item in value:visit(item)
    visit(graph)
    selected={}
    for key,count in counts.items():
        if count>=2 and (count-1)*len(key)>count*18+40:
            selected[key]=len(selected)
    if not selected:return graph
    def replace(value):
        key=signature(value)
        if key in selected:return {'shared':selected[key]}
        if isinstance(value,dict):return {k:replace(v) for k,v in value.items()}
        if isinstance(value,list):return [replace(v) for v in value]
        return value
    packed=replace(graph)
    packed['shared_values']=[values[key] for key in selected]
    packed['encoding']=packed.get('encoding','')+' Objects {shared:n} reuse shared_values[n] exactly; expand them before interpreting fields or links.'
    return packed if len(json.dumps(packed,ensure_ascii=False))<len(json.dumps(graph,ensure_ascii=False)) else graph

def model_graph_context(graph, sources=None):
    """Group repeated provenance and field names; preserve all values and edges."""
    def table(records):
        columns=list(dict.fromkeys(key for row in records for key in row))
        constants={key:records[0][key] for key in columns if key not in {'id','from_id','to_id'}
                   and key in records[0] and all(key in row and row[key]==records[0][key] for row in records)} if records else {}
        columns=[key for key in columns if key not in constants]
        return dict(columns=columns,constants=constants,rows=[[row.get(key) for key in columns] for row in records])
    def shortest_groups(rows):
        choices=[[table(rows)]]
        for keys in [('evidence_ids',),('origin','review_status','role','meaning'),
                     ('reading_stream_id',),('evidence_ids','reading_stream_id'),('page_number','kind')]:
            groups={}
            for row in rows:
                signature=json.dumps([row.get(key) for key in keys],ensure_ascii=False,sort_keys=True)
                groups.setdefault(signature,[]).append(row)
            choices.append([table(group) for group in groups.values()])
        sparse={}
        for row in rows:sparse.setdefault(tuple(sorted(row)),[]).append(row)
        choices.append([table(group) for group in sparse.values()])
        return min(choices,key=lambda value:len(json.dumps(value,ensure_ascii=False,separators=(',',':'))))
    grids=[];encoded=False;inferred_bindings=False
    if sources is not None:
        graph,grids=_prompt_graph_tables(graph)
        nodes_by_id={node['id']:node for node in graph.get('nodes',[])}
        edges=[]
        for edge in graph.get('edges',[]):
            endpoints=[nodes_by_id.get(edge.get(k),{}) for k in ('from_id','to_id')]
            bindings=[set(node.get('evidence_ids',[])) for node in endpoints]
            implied=sorted(set.intersection(*bindings) or set.union(*bindings))
            if implied and edge.get('evidence_ids')==implied:
                edge={k:v for k,v in edge.items() if k!='evidence_ids'}
                inferred_bindings=True
            edges.append(edge)
        graph=dict(graph,edges=edges)
        def source_reference(value):
            if isinstance(value,dict):return {k:source_reference(v) for k,v in value.items()}
            if isinstance(value,list):return [source_reference(v) for v in value]
            if isinstance(value,str) and len(value)>80:
                for source in sources:
                    text=source.get('text','');start=text.find(value)
                    if start<0:continue
                    reference=dict(source=source['evidence_id'])
                    if value!=text:reference['span']=[start,start+len(value)]
                    if len(json.dumps(reference))<len(json.dumps(value,ensure_ascii=False)):return reference
            return value
        referenced=source_reference(graph)
        encoded=bool(grids) or referenced!=graph
        graph=referenced
    by_kind={}
    for edge in graph.get('edges',[]):
        by_kind.setdefault(edge['type'],[]).append({key:value for key,value in edge.items() if key!='type'})
    relations={kind:shortest_groups(edges) for kind,edges in by_kind.items()}
    if sources is not None:
        for kind,edges in by_kind.items():
            groups={}
            for edge in edges:
                fields={k:v for k,v in edge.items() if k not in {'from_id','to_id'}}
                signature=json.dumps(fields,ensure_ascii=False,sort_keys=True)
                constants,links=groups.setdefault(signature,(fields,{}))
                links.setdefault(edge['from_id'],[]).append(edge['to_id'])
            adjacency=[dict(constants=constants,links=[[a,bs] for a,bs in links.items()])
                       for constants,links in groups.values()]
            size=lambda value:len(json.dumps(value,ensure_ascii=False,separators=(',',':')))
            if size(adjacency)<size(relations[kind]):
                relations[kind]=adjacency
                encoded=True
    node_groups={}
    for node in graph.get('nodes',[]):
        node_groups.setdefault(node.get('kind'),[]).append(node)
    packed=[]
    for rows in node_groups.values():
        packed.extend(shortest_groups(rows))
    result=dict(nodes=dict(groups=packed),relations=relations,
        relation_legend=graph.get('relation_legend',{}),
        coverage={key:value for key,value in graph.items() if key not in {'nodes','edges','relation_legend'}})
    if grids:result['table_grids']=grids
    if inferred_bindings:
        result['edge_source_default']='An edge without evidence_ids inherits the nonempty intersection of endpoint node evidence_ids; if the intersection is empty, use their union. Explicit evidence_ids override this default.'
    if encoded:
        result['encoding']=(
            'Group constants apply to every row/link. links are [from_id,[to_ids]]. '
            'A value {source:E1} reuses that source passage verbatim; span:[start,end] selects its '
            'zero-based Unicode character interval, end exclusive. These are text references, not new facts. '
            'table_grids replace isolated HAS_ROW/HAS_CELL branches: rows are [row_number,cells]; '
            'cells are [column_number,text,rowspan?,colspan?], spans default to 1. '
            'Keep the native row/column numbers and merged cells. Row/cell defaults and HAS_ROW/HAS_CELL '
            'metadata apply throughout that grid. All other graph links remain explicit.')
    return _share_graph_values(result) if sources is not None else result


