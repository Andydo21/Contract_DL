"""Persist expert attachments and a separate, tenant-scoped semantic graph."""
import hashlib
import uuid
import re
from pathlib import Path
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from contracts.models import Contract, ContractVersion, ContractFile
from contracts.services.document_encryption_service import encrypt_pdf


def text_record(record):
    """Stable source identity plus a fingerprint checked before using a hit."""
    import json
    record = dict(record, source_kind='knowledge_text')
    record['content_sha256'] = hashlib.sha256(json.dumps(record, sort_keys=True,
        ensure_ascii=False, default=str).encode()).hexdigest()
    return record


def submission_records(receipt):
    """Use original Q/A and verified quotes; titles are navigation, not facts."""
    data = receipt.result.get('request', {})
    company = data.get('company_id')
    if not company or receipt.user.company_id != company:
        return []
    root = f'a2-expert:{company}:{receipt.pk}'
    # Preserve explicitly marked sample provenance for the whole submission,
    # including semantic units whose short quote omits the original marker.
    is_demo = data.get('is_demo') is True or any(
        re.search(r'^\s*(?:\[DEMO\]|DEMO\s*:|Mẫu trả lời demo\s*:)', data.get(key, ''), re.I | re.M)
        for key in ('answer', 'note'))
    common = dict(company_id=company, submission_id=receipt.pk, document_id=root,
        contract_id=None, version_id=None, page_number=1, bbox=[], layout_type='expert_text',
        author=receipt.user.username, review_status='draft', is_demo=bool(is_demo),
        source_url=f'/newidea/?submission_id={receipt.pk}#expert-submission',
        source_location=f'Expert submission {receipt.pk}', original_name=f'Expert: {receipt.user.username}',
        heading_path=[], ancestor_ids=[], question=receipt.query)
    source_texts = {'question': receipt.query, 'expert-answer': data.get('answer', ''),
                    'expert-note': data.get('note', '')}
    records = []
    for source, text in source_texts.items():
        if text.strip():
            key = root+':'+source
            records.append(text_record(dict(common, knowledge_key=key, chunk_id=key,
                text=text, evidence_kind='expert_question' if source=='question' else 'expert_unit',
                source_role=source, heading_path=[receipt.query],
                graph_node_key=root if source=='question' else root+':answer' if source=='expert-answer' else root)))
    for unit in receipt.result.get('semantic_analysis', {}).get('units', []):
        source = unit.get('source_id', '').rsplit(':', 1)[0]
        quote = unit.get('quote', '')
        if not quote or source in source_texts and quote not in source_texts[source]:
            continue
        # Document quotes already have source pointers recorded by validation.
        if source not in source_texts and not unit.get('snapshot_key'):
            continue
        key = root+':'+unit['id']
        records.append(text_record(dict(common, knowledge_key=key, chunk_id=key, text=quote,
            evidence_kind='expert_question' if source=='question' else 'expert_unit',
            source_role=source, graph_node_key=key, unit_kind=unit['kind'],
            source_chunk_id=unit.get('source_chunk_id', ''),
            source_url=unit.get('source_url') or common['source_url'],
            heading_path=[receipt.query, unit['title']], concepts=unit.get('concepts', []))))
    return records


def visible_text_records(user):
    """Reload source records for access checks and stale-vector rejection."""
    from contracts.models import KnowledgeSearchLog
    from .contract_repository import approved_visible_cases
    from NewIdea.services.case_rules import serialize_case
    from NewIdea.services.evidence_service import evidence_current
    from NewIdea.services.search_evidence_service import with_expert_evidence
    jobs = KnowledgeSearchLog.objects.filter(scope='expert', status='COMPLETED').select_related('user')
    if not user.is_authenticated:
        return []
    if not user.is_superuser:
        if not user.company_id:
            return []
        jobs = jobs.filter(result__request__company_id=user.company_id)
    records = [record for receipt in jobs for record in submission_records(receipt)]
    for case in approved_visible_cases(user):
        if not evidence_current(case):
            continue
        details = serialize_case(case)
        evidence = with_expert_evidence([], [details])[0]
        evidence.pop('evidence_id', None)
        records.append(text_record(dict(evidence, knowledge_key=evidence['chunk_id'],
            company_id=case.version.contract.company_id, document_id='a2-case:'+str(case.case_id),
            review_status=case.status, expert_case=details, page_number=1, bbox=[])))
    return records


def submission_context(receipt, records):
    """Source-bound saved graph edges, including ANSWERS and shared concepts."""
    if receipt.result.get('graph_index', {}).get('status') == 'cleared':
        return dict(state='cleared', version_id=None, nodes=[], edges=[],
                    origin='explicit_graph_reset')
    root = f'a2-expert:{receipt.result["request"]["company_id"]}:{receipt.pk}'
    nodes, edges = {}, []
    by_graph = {}
    for record in records:
        if record.get('submission_id') != receipt.pk:
            continue
        key = record['graph_node_key']
        by_graph.setdefault(key, []).append(record)
        node = nodes.setdefault(key, dict(id=key, kind=record.get('unit_kind', record['source_role']),
            label=record.get('text', '')[:100], source_leaf_ids=[]))
        node['source_leaf_ids'].append(record['chunk_id'])
    for relation in receipt.result.get('semantic_analysis', {}).get('relations', []):
        source = root if relation['from_id']=='question' else root+':'+relation['from_id']
        target = root if relation['to_id']=='question' else root+':'+relation['to_id']
        if source in by_graph and target in by_graph:
            edges.append(dict(from_id=source, to_id=target, type=relation['kind'], review_status='unreviewed',
                source_leaf_ids=[r['chunk_id'] for endpoint in (source, target) for r in by_graph[endpoint]]))
    return dict(state='ready', version_id=None, nodes=list(nodes.values()), edges=edges,
                origin='persisted_a2_graph_proposals', review_status='draft')


def contexts_for_records(records):
    from contracts.models import KnowledgeSearchLog
    identities = {r['submission_id'] for r in records if r.get('submission_id')}
    jobs = KnowledgeSearchLog.objects.filter(pk__in=identities, status='COMPLETED', scope='expert')
    return [submission_context(receipt, records) for receipt in jobs]


def visible_submission(user, identity):
    from contracts.models import KnowledgeSearchLog
    rows = KnowledgeSearchLog.objects.filter(scope='expert', status='COMPLETED').select_related('user')
    if not user.is_superuser:
        rows = rows.filter(result__request__company_id=user.company_id) if user.company_id else rows.none()
    receipt = rows.get(pk=identity)
    if not submission_records(receipt):
        raise KnowledgeSearchLog.DoesNotExist
    data = receipt.result['request']
    return dict(success=True, submission_id=receipt.pk, author=receipt.user.username, review_status='draft',
        question=receipt.query, answer=data.get('answer', ''), note=data.get('note', ''),
        units=receipt.result.get('semantic_analysis', {}).get('units', []),
        relations=receipt.result.get('semantic_analysis', {}).get('relations', []),
        qwen_outputs=receipt.result.get('qwen_outputs', []),
        vector_index=receipt.result.get('semantic_index', {}))


def store_attachment(user, uploaded, saved_paths):
    name = Path(uploaded.name.replace('\\', '/')).name
    content = uploaded.read()
    path = default_storage.save(f'contracts/expert/{uuid.uuid4().hex}/{name}', ContentFile(encrypt_pdf(content)))
    saved_paths.append(path)
    contract = Contract.objects.create(company_id=user.company_id, contract_code='EXP-'+uuid.uuid4().hex[:20],
        title=name[:255], contract_type='Expert attachment', status='DRAFT')
    version = ContractVersion.objects.create(contract=contract, version_number=1,
        file_hash=hashlib.sha256(content).hexdigest(), change_summary='Expert attachment uploaded by '+user.username)
    ContractFile.objects.create(version=version, file_name=name, file_path=default_storage.url(path),
                                file_size=len(content), mime_type=uploaded.content_type or '')
    return version


def cleanup_uploads(paths):
    for path in paths:
        default_storage.delete(path)


def sync_semantic_graph(receipt, units, relations, document_scopes):
    from ai_extract.repositories.document_graph_repository import connection
    company = receipt.result['request']['company_id']
    root = f'a2-expert:{company}:{receipt.pk}'
    nodes = [dict(key=root+':'+u['id'], submission_key=root, company_id=company,
        kind=u['kind'], title=u['title'], quote=u['quote'], source_id=u['source_id'],
        source_url=u.get('source_url', ''), source_chunk_id=u.get('source_chunk_id', ''),
        author_id=receipt.user_id, review_status='draft') for u in units]
    edges = [dict(from_key=root if r['from_id']=='question' else root+':'+r['from_id'],
                  to_key=root if r['to_id']=='question' else root+':'+r['to_id'], kind=r['kind']) for r in relations]
    def write(tx):
        tx.run('MERGE (q:A2ExpertQuestion {key:$key}) SET q.company_id=$company,q.author_id=$author,'
               'q.question=$question,q.note=$note,q.review_status="draft"', key=root, company=company,
               author=receipt.user_id, question=receipt.query, note=receipt.result['request']['note']).consume()
        tx.run('MATCH (n:A2SemanticUnit {submission_key:$key}) DETACH DELETE n', key=root).consume()
        tx.run('MATCH (n:A2ExpertAnswer {submission_key:$key}) DETACH DELETE n', key=root).consume()
        if receipt.result['request'].get('answer'):
            tx.run('CREATE (a:A2ExpertAnswer {key:$answer_key,submission_key:$key,company_id:$company,'
                   'author_id:$author,text:$answer,review_status:"draft"})', answer_key=root+':answer',
                   key=root, company=company, author=receipt.user_id, answer=receipt.result['request']['answer']).consume()
        tx.run('MATCH (q:A2ExpertQuestion {key:$key})-[r:HAS_DOCUMENT]->() DELETE r', key=root).consume()
        tx.run('UNWIND $nodes AS row CREATE (n:A2SemanticUnit) SET n=row '
               'WITH n MATCH (q:A2ExpertQuestion {key:$key}) CREATE (q)-[:HAS_UNIT]->(n)', nodes=nodes, key=root).consume()
        for kind in ('ASKS_ABOUT', 'SUPPORTED_BY', 'QUALIFIES', 'CONTRADICTS', 'ANSWERS', 'HAS_UNIT'):
            tx.run('UNWIND $rows AS row MATCH (a {key:row.from_key}), (b {key:row.to_key}) '
                   'WHERE a.company_id=$company AND b.company_id=$company '
                   f'MERGE (a)-[:{kind} {{origin:"explicit_submission_binding",review_status:"draft"}}]->(b)',
                   rows=[r for r in edges if r['kind']==kind], company=company).consume()
        for unit in units:
            for concept in unit.get('concepts', []):
                # Hash includes kind and the literal normalized phrase. Company
                # is part of identity; shared vocabulary is not shared advice.
                concept_key=f'a2-concept:{company}:{concept["id"]}'
                tx.run('MERGE (c:A2Concept {key:$concept}) ON CREATE SET c.company_id=$company,'
                       'c.kind=$kind,c.value=$value '
                       'WITH c MATCH (u:A2SemanticUnit {key:$unit,company_id:$company}) '
                       f'MERGE (u)-[r:{concept["relation"]}]->(c) '
                       'SET r.quote=$quote,r.origin="source_grounded_term",r.review_status="draft"',
                       concept=concept_key,company=company,kind=concept['kind'],value=concept['value'],
                       unit=root+':'+unit['id'],quote=concept['quote']).consume()
        for scope in document_scopes:
            tx.run('MATCH (q:A2ExpertQuestion {key:$key}), (s:A3Snapshot {key:$snapshot,company_id:$company}) '
                   'MERGE (q)-[:HAS_DOCUMENT {origin:"expert_selected_or_uploaded_attachment"}]->(s)',
                   key=root, snapshot=scope['key'], company=company).consume()
            tx.run('MATCH (a:A2ExpertAnswer {key:$answer,company_id:$company}), '
                   '(s:A3Snapshot {key:$snapshot,company_id:$company}) '
                   'MERGE (a)-[:HAS_DOCUMENT {origin:"expert_attachment_not_verified_evidence"}]->(s)',
                   answer=root+':answer', snapshot=scope['key'],company=company).consume()
            for unit in units:
                if unit.get('snapshot_key') != scope['key']:
                    continue
                tx.run('MATCH (u:A2SemanticUnit {key:$unit,company_id:$company}), '
                       '(s:A3Snapshot {key:$snapshot,company_id:$company}) '
                       'MERGE (u)-[:HAS_EVIDENCE {origin:"exact_quote_in_document_source"}]->(s)',
                       unit=root+':'+unit['id'], company=company, snapshot=scope['key']).consume()
                tx.run('MATCH (u:A2SemanticUnit {key:$unit,company_id:$company}), '
                       '(b:A3Node {snapshot_key:$snapshot}) '
                       'WHERE b.key=$block OR (b.category="evidence" AND b.source_id=$source '
                       'AND b.text CONTAINS $quote) '
                       'MERGE (u)-[:HAS_EVIDENCE {origin:"exact_quote_in_extracted_block"}]->(b)',
                       unit=root+':'+unit['id'], company=company, snapshot=scope['key'], block=unit['graph_block_key'],
                       source=unit.get('source_chunk_id',''),quote=unit['quote']).consume()
    with connection() as session:
        for label in ('A2ExpertQuestion', 'A2ExpertAnswer', 'A2SemanticUnit', 'A2Concept'):
            session.run(f'CREATE CONSTRAINT {label.lower()}_key IF NOT EXISTS '
                        f'FOR (n:{label}) REQUIRE n.key IS UNIQUE').consume()
        session.execute_write(write)
        counts = session.run('MATCH (q:A2ExpertQuestion {key:$key}) '
            'RETURN COUNT { (q)-[:HAS_UNIT]->() } AS units, '
            'COUNT { (q)-[:HAS_DOCUMENT]->() } AS documents', key=root).single()
        evidence = session.run('MATCH (u:A2SemanticUnit {submission_key:$key})-[r:HAS_EVIDENCE]->() '
                               'RETURN count(r) AS links', key=root).single()['links']
        missing = session.run('UNWIND $keys AS key MATCH (u:A2SemanticUnit {key:key}) '
            'WHERE NOT (u)-[:HAS_EVIDENCE]->(:A3Node) RETURN count(u) AS missing',
            keys=[root+':'+u['id'] for u in units if u.get('snapshot_key')]).single()['missing']
    complete = counts['units'] == len(nodes) and counts['documents'] == len(document_scopes) and missing == 0
    return dict(status='ready' if complete else 'partial', key=root, units=counts['units'],
                proposed_relations=len(edges), documents=counts['documents'], evidence_links=evidence,
                missing_source_units=missing, review_status='draft')


def related_units(receipt, limit=12):
    """Same-company shared-term navigation, including explicitly marked drafts."""
    from ai_extract.repositories.document_graph_repository import connection
    company=receipt.result['request']['company_id']
    root=f'a2-expert:{company}:{receipt.pk}'
    query='''
    MATCH (seed:A2SemanticUnit {submission_key:$root,company_id:$company})
          -[:ABOUT_MACHINE|HAS_ACTION|HAS_SOLUTION]->(c:A2Concept {company_id:$company})
          <-[:ABOUT_MACHINE|HAS_ACTION|HAS_SOLUTION]-(other:A2SemanticUnit {company_id:$company})
    WHERE other.submission_key<>$root
    WITH other,collect(DISTINCT {kind:c.kind,value:c.value}) AS common
    RETURN other.key AS key,other.submission_key AS submission_key,other.title AS title,
           other.quote AS quote,other.source_url AS source_url,other.review_status AS review_status,common
    ORDER BY size(common) DESC,key LIMIT $limit
    '''
    with connection() as session:
        return [dict(row) for row in session.run(query,root=root,company=company,limit=min(30,max(1,limit)))]
