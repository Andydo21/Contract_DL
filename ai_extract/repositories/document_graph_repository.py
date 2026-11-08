"""Parameterized Neo4j storage for one immutable, tenant-scoped A3 snapshot."""
from contextlib import contextmanager
from itertools import zip_longest
from threading import Lock
import atexit
import json
from django.conf import settings
from ai_extract import SEMANTIC_EDGE_TYPES, RETRIEVAL_EDGE_TYPES, VISUAL_SOURCE_EDGE_TYPES

_driver = None
_driver_settings = None
_driver_lock = Lock()


def close_driver():
    global _driver, _driver_settings
    with _driver_lock:
        if _driver is not None:
            _driver.close()
        _driver = _driver_settings = None


atexit.register(close_driver)

@contextmanager
def connection():
    """Share Neo4j's thread-safe pool; sessions remain scoped to each operation."""
    global _driver, _driver_settings
    from neo4j import GraphDatabase
    uri = getattr(settings, 'NEO4J_URI', '')
    password = getattr(settings, 'NEO4J_PASSWORD', '')
    if not uri or not password:
        raise RuntimeError('Neo4j connection is not configured')
    config = (uri, getattr(settings, 'NEO4J_USER', 'neo4j'), password)
    with _driver_lock:
        if _driver is None or _driver_settings != config:
            if _driver is not None:
                _driver.close()
            _driver = GraphDatabase.driver(uri, auth=config[1:], connection_timeout=10,
                connection_acquisition_timeout=30, max_transaction_retry_time=30)
            _driver_settings = config
        driver = _driver
    with driver.session(database=getattr(settings, 'NEO4J_DATABASE', 'neo4j')) as session:
        yield session


def passage_pair_rejection(source_id,target_id,quote,target_quote,pairs,targets):
    """Admission check only; never remove or rewrite an existing edge."""
    source_text=' '.join(quote.split());target_text=' '.join(target_quote.split())
    if source_id==target_id:return 'self_pair'
    if source_text==target_text:return 'identical_text'
    if frozenset((source_id,target_id)) in pairs:return 'reciprocal_or_duplicate'
    if (source_id,target_text) in targets:return 'repeated_target_text'
    return None


def validate_passage_links(links,from_field='from_id',to_field='to_id'):
    """Reject a duplicate batch before projection or any database mutation."""
    pairs=set();targets=set()
    for link in links:
        source,target=link[from_field],link[to_field]
        reason=passage_pair_rejection(source,target,link['quote'],link['target_quote'],pairs,targets)
        if reason:raise ValueError('Rejected RELATED_PASSAGE: '+reason)
        pairs.add(frozenset((source,target)));targets.add((source,' '.join(link['target_quote'].split())))


# Document text lives in PostgreSQL only (extraction blocks, the run's source tree, clauses). The graph keeps ids,
# kinds, titles and positions; every reader takes the words from PostgreSQL by those ids, so no second plaintext copy
# of a contract sits in the graph store.
NODE_TEXT_FIELDS = ('text', 'content', 'in_image_text_json', 'summary_description', 'caption_text')
EDGE_TEXT_FIELDS = ('quote', 'target_quote', 'scope_quote', 'condition_quotes', 'qualification_quote')


def without_text(rows, fields):
    return [{k: v for k, v in row.items() if k not in fields} for row in rows]


def replace_snapshot(scope, nodes, edges):
    """Replace atomically; retries neither duplicate edges nor expose half a tree."""
    validate_passage_links([e for e in edges if e['type']=='RELATED_PASSAGE'],'from_key','to_key')
    nodes, edges = without_text(nodes, NODE_TEXT_FIELDS), without_text(edges, EDGE_TEXT_FIELDS)
    if len({n['key'] for n in nodes})!=len(nodes):raise ValueError('Duplicate graph node keys')
    keys={n['key'] for n in nodes}
    if any(n.get('snapshot_key')!=scope.get('key') or not n['key'].startswith(str(scope.get('key'))+':') for n in nodes):
        raise ValueError('Graph nodes must belong to the same document snapshot')
    if any(e.get('from_key') not in keys or e.get('to_key') not in keys for e in edges):
        raise ValueError('Cross-document or missing graph endpoints are forbidden')
    if not scope.get('entity_compacted') and any(n.get('category')=='entity' and n.get('canonical_key') for n in nodes):
        raise ValueError('Shared entity registry writes are retired; prepare document-local identities first')
    def write(tx):
        tx.run("MERGE (s:A3Snapshot {key:$scope.key}) SET s += $scope, s.entity_resolution_state=$state, s.entity_resolution_attempts=0, s.entity_resolution_claim=null, s.entity_resolution_lease=null",scope=scope,
               state='complete' if scope.get('identity_prepared') else 'pending').consume()
        tx.run('MATCH (n:A3Node {snapshot_key:$key}) DETACH DELETE n', key=scope['key']).consume()
        tx.run('UNWIND $rows AS row CREATE (n:A3Node) SET n = row REMOVE n.identity_embedding', rows=nodes).consume()
        for kind in dict.fromkeys(('CONTAINS', 'HAS_EVIDENCE', 'MENTIONS', 'RELATED', 'HAS_VISUAL', 'APPEARS_IN', 'EXPLAINS', 'LEFT_OF', 'ABOVE', 'NEAR', 'NEXT', 'HAS_ROW', 'HAS_CELL', 'HAS_EMBEDDING', 'HAS_CLAUSE', 'HAS_PARTY', 'NAMES_PARTY',*SEMANTIC_EDGE_TYPES,*RETRIEVAL_EDGE_TYPES,*VISUAL_SOURCE_EDGE_TYPES)):
            rows = [e for e in edges if e['type'] == kind]
            # Only application-owned relationship types are interpolated.
            tx.run('UNWIND $rows AS row MATCH (a:A3Node {key:row.from_key, snapshot_key:$key}), '
                   '(b:A3Node {key:row.to_key, snapshot_key:$key}) '
                   f'CREATE (a)-[r:{kind}]->(b) SET r.predicate=row.predicate, '
                   'r.quote=row.quote, r.source_leaf_id=row.source_leaf_id, r.origin=row.origin, '
                   'r.structure_review_status=row.structure_review_status, r.source_review_status=row.source_review_status, '
                   'r.review_origin=row.review_origin, r.review_evidence_json=row.review_evidence_json, '
                   'r.target_quote=row.target_quote, r.threshold=row.threshold, r.review_status=row.review_status, '
                   'r.polarity=row.polarity, r.modality=row.modality, r.condition_quotes=row.condition_quotes, '
                   'r.scope_quote=row.scope_quote, r.qualification_quote=row.qualification_quote, r.confidence=row.confidence, '
                   'r.qualification_validation=row.qualification_validation, r.relation_review_json=row.relation_review_json, r.reading_stream_id=row.reading_stream_id, '
                   'r.occurrence_key=row.occurrence_key, r.target_source_leaf_id=row.target_source_leaf_id, r.from_char_start=row.from_char_start, '
                   'r.from_char_end=row.from_char_end, r.to_char_start=row.to_char_start, r.to_char_end=row.to_char_end, '
                   'r.dense_similarity=row.dense_similarity, r.rerank_logit=row.rerank_logit, r.retrieval_rank=row.retrieval_rank, '
                   'r.relation_semantics=row.relation_semantics, r.score_semantics=row.score_semantics, r.reference_type=row.reference_type, r.mention=row.mention, r.matched_title=row.matched_title',
                   rows=rows, key=scope['key']).consume()
        # A growing extraction has a new source fingerprint after each page.
        # Prune only older snapshots of this exact tenant/version/run, in the
        # same transaction after the new projection has been written.
        tx.run('MATCH (s:A3Snapshot) WHERE s.company_id=$scope.company_id '
               'AND s.contract_id=$scope.contract_id AND s.version_id=$scope.version_id '
               'AND s.run_id=$scope.run_id AND s.key<>$scope.key '
               'OPTIONAL MATCH (n:A3Node {snapshot_key:s.key}) '
               'DETACH DELETE n, s', scope=scope).consume()
    with connection() as session:
        session.run('CREATE CONSTRAINT a3_snapshot_key IF NOT EXISTS FOR (s:A3Snapshot) REQUIRE s.key IS UNIQUE').consume()
        session.run('CREATE CONSTRAINT a3_node_key IF NOT EXISTS FOR (n:A3Node) REQUIRE n.key IS UNIQUE').consume()
        session.run('CREATE INDEX a3_node_snapshot IF NOT EXISTS FOR (n:A3Node) ON (n.snapshot_key)').consume()
        session.run('CREATE CONSTRAINT a3_entity_key IF NOT EXISTS FOR (e:A3Entity) REQUIRE e.key IS UNIQUE').consume()
        session.execute_write(write)


def contract_outline(scope):
    """Clause order, parties, entities and passage links of one exact snapshot."""
    def read(tx):
        snapshot=tx.run('''MATCH (s:A3Snapshot {key:$scope.key})
            WHERE s.company_id=$scope.company_id AND s.contract_id=$scope.contract_id
              AND s.version_id=$scope.version_id AND s.run_id=$scope.run_id AND s.fingerprint=$scope.fingerprint
            RETURN s.key AS key''',scope=scope).single()
        if not snapshot:return dict(clauses=[],parties=[],related_passages=[],references=[])
        clauses=tx.run('''MATCH (c:A3Node {snapshot_key:$key,category:'contract_clause'})
            OPTIONAL MATCH (c)-[:HAS_EVIDENCE]->(e:A3Node {snapshot_key:$key,category:'evidence'})
            OPTIONAL MATCH (e)-[:MENTIONS]->(m:A3Node {snapshot_key:$key,category:'entity'})
            WITH c,collect(DISTINCT e.leaf_id) AS leaf_ids,collect(DISTINCT m.name) AS entities
            OPTIONAL MATCH (b:A3Node {snapshot_key:$key,category:'layout_block'})-[:CONTAINS]->(c)
            WITH c,leaf_ids,entities,collect(DISTINCT b.key) AS blocks
            RETURN c.ordinal AS ordinal,c.title AS title,leaf_ids,entities,blocks ORDER BY ordinal''',key=scope['key']).data()
        parties=tx.run('''MATCH (p:A3Node {snapshot_key:$key,is_party:true})
            RETURN p.role AS role,p.name AS name ORDER BY p.key''',key=scope['key']).data()
        passages=tx.run('''MATCH (a:A3Node {snapshot_key:$key})-[:RELATED_PASSAGE]->(b:A3Node {snapshot_key:$key})
            RETURN a.leaf_id AS left,b.leaf_id AS right''',key=scope['key']).data()
        references=tx.run('''MATCH (a:A3Node {snapshot_key:$key,category:'evidence'})-[:REFERENCES]->(b:A3Node {snapshot_key:$key,category:'evidence'})
            RETURN a.leaf_id AS left,b.leaf_id AS right''',key=scope['key']).data()
        return dict(clauses=clauses,parties=parties,related_passages=[(row['left'],row['right']) for row in passages],
                    references=[(row['left'],row['right']) for row in references])
    with connection() as session:
        return session.execute_read(read)


def reset_contract_graph(company_id,contract_id,known_keys=()):
    """Remove only this authorized document's snapshots and unshared identities."""
    def write(tx):
        rows=tx.run('''MATCH (s:A3Snapshot {company_id:$company,contract_id:$contract})
            RETURN s.key AS key''',company=company_id,contract=contract_id).data()
        keys=sorted(set(known_keys)|{r['key'] for r in rows})
        others=tx.run('''MATCH (n:A3Node) WHERE NOT n.snapshot_key IN $keys
            RETURN count(n) AS count''',keys=keys).single()['count']
        before=tx.run('''MATCH (n:A3Node) WHERE n.snapshot_key IN $keys
            OPTIONAL MATCH (n)-[r]-() RETURN count(DISTINCT n) AS nodes,count(DISTINCT r) AS edges''',keys=keys).single()
        canonical=tx.run('''MATCH (n:A3Node)-[:RESOLVES_TO]->(e:A3Entity {company_id:$company})
            WHERE n.snapshot_key IN $keys RETURN DISTINCT e.key AS key''',keys=keys,company=company_id).data()
        tx.run('MATCH (n:A3Node) WHERE n.snapshot_key IN $keys DETACH DELETE n',keys=keys).consume()
        tx.run('''MATCH (s:A3Snapshot {company_id:$company,contract_id:$contract})
            DETACH DELETE s''',company=company_id,contract=contract_id).consume()
        deleted=tx.run('''MATCH (e:A3Entity {company_id:$company}) WHERE e.key IN $keys
            AND NOT EXISTS {MATCH (:A3Node)-[:RESOLVES_TO]->(e)}
            WITH collect(e) AS entities, count(e) AS count
            FOREACH (e IN entities | DETACH DELETE e) RETURN count''',
            company=company_id,keys=[r['key'] for r in canonical]).single()['count']
        remaining=tx.run('MATCH (n:A3Node) WHERE n.snapshot_key IN $keys RETURN count(n) AS count',keys=keys).single()['count']
        after=tx.run('''MATCH (n:A3Node) WHERE NOT n.snapshot_key IN $keys
            RETURN count(n) AS count''',keys=keys).single()['count']
        remaining_snapshots=tx.run('''MATCH (s:A3Snapshot {company_id:$company,contract_id:$contract})
            RETURN count(s) AS count''',company=company_id,contract=contract_id).single()['count']
        if remaining or remaining_snapshots or others!=after:raise ValueError('Graph reset scope verification failed; rolled back')
        return dict(deleted_snapshots=len(rows),deleted_nodes=before['nodes'],deleted_edges=before['edges'],
            deleted_unshared_identities=deleted,remaining_nodes=remaining,remaining_snapshots=remaining_snapshots,
            unrelated_nodes_before=others,unrelated_nodes_after=after)
    with connection() as session:
        return session.execute_write(write)


def replace_cross_document_links(snapshot_key, edges):
    """Citation edges between two documents' snapshots. Every such edge touching this snapshot, in either
    direction, is replaced: the caller rebuilds both directions from the citations each document keeps."""
    rows = [dict(e, articles=[int(a) for a in e.get('articles', [])], paragraphs=[int(p) for p in e.get('paragraphs', [])]) for e in edges]
    def write(tx):
        tx.run('MATCH (:A3Node {snapshot_key:$key})-[r:REFERENCES {cross_document:true}]-() DELETE r', key=snapshot_key).consume()
        row = tx.run('UNWIND $rows AS row MATCH (a:A3Node {key:row.from_key}), (b:A3Node {key:row.to_key}) '
                     'CREATE (a)-[r:REFERENCES]->(b) SET r.cross_document=true, r.origin=\'gliner2_cross_document_citation\', '
                     'r.review_status=\'unreviewed\', r.predicate=\'references\', r.mention=row.mention, r.law=row.law, '
                     'r.articles=row.articles, r.paragraphs=row.paragraphs, r.reference_type=row.reference_type, '
                     'r.source_leaf_id=row.source_leaf_id, r.target_source_leaf_id=row.target_source_leaf_id, '
                     'r.from_run=row.from_run, r.to_run=row.to_run RETURN count(r) AS written', rows=rows).single()
        return row['written'] if row else 0
    with connection() as session:
        return session.execute_write(write)


def prune_old_runs(scope):
    """Keep the newest completed graph; never delete another version/tenant."""
    def write(tx):
        row = tx.run('''
            MATCH (current:A3Snapshot {key:$scope.key})
            WHERE current.company_id=$scope.company_id AND current.contract_id=$scope.contract_id
              AND current.version_id=$scope.version_id AND current.run_id=$scope.run_id
              AND current.fingerprint=$scope.fingerprint
              AND EXISTS { MATCH (:A3Node {snapshot_key:current.key}) }
            SET current.completed=true
            WITH current
            MATCH (keep:A3Snapshot)
            WHERE keep.company_id=current.company_id AND keep.contract_id=current.contract_id
              AND keep.version_id=current.version_id AND keep.completed=true
            WITH keep ORDER BY keep.run_id DESC LIMIT 1
            MATCH (old:A3Snapshot)
            WHERE old.company_id=keep.company_id AND old.contract_id=keep.contract_id
              AND old.version_id=keep.version_id AND old.run_id<keep.run_id
            WITH collect(old.key) AS keys
            CALL (keys) {
              MATCH (old:A3Snapshot) WHERE old.key IN keys
              OPTIONAL MATCH (n:A3Node {snapshot_key:old.key})
              DETACH DELETE n, old
            }
            RETURN size(keys) AS deleted_snapshots
        ''',scope=scope).single()
        tx.run('''MATCH (e:A3Entity {company_id:$company})
          WHERE NOT EXISTS { MATCH (:A3Node)-[:RESOLVES_TO]->(e) }
          AND NOT (coalesce(e.identity_model,'') IN ['fastino/gliner2-base-v1','fastino/gliner2-multi-v1']
                   AND size(coalesce(e.identity_anchors,[]))>0)
          DETACH DELETE e''',company=scope['company_id']).consume()
        return row['deleted_snapshots'] if row else 0
    with connection() as session:
        return session.execute_write(write)


def entity_schema():
    """Indexes are independent of extraction snapshots and source-node cleanup."""
    with connection() as session:
        for query in (
            'CREATE CONSTRAINT a3_entity_queue_key IF NOT EXISTS FOR (q:A3EntityQueue) REQUIRE q.key IS UNIQUE',
            'CREATE CONSTRAINT a3_entity_scope IF NOT EXISTS FOR (s:A3EntityScope) REQUIRE s.company_id IS UNIQUE',
            'CREATE CONSTRAINT a3_entity_key IF NOT EXISTS FOR (e:A3Entity) REQUIRE e.key IS UNIQUE',
            'CREATE INDEX a3_identity_jobs IF NOT EXISTS FOR (s:A3Snapshot) ON (s.completed,s.entity_resolution_state)',
            'CREATE INDEX a3_entity_company IF NOT EXISTS FOR (e:A3Entity) ON (e.company_id, e.entity_type)',
            'CREATE FULLTEXT INDEX a3_entity_names IF NOT EXISTS FOR (e:A3Entity) ON EACH [e.lookup_scope,e.name,e.aliases]',
            "CREATE VECTOR INDEX a3_entity_vectors IF NOT EXISTS FOR (e:A3Entity) ON (e.embedding) OPTIONS {indexConfig: {`vector.dimensions`:1024, `vector.similarity_function`:'cosine'}}",
        ):
            session.run(query).consume()


def claim_entity_job():
    """Durable pending jobs; a lease permits recovery after a worker crash."""
    def write(tx):
        from uuid import uuid4
        token=str(uuid4())
        tx.run("MERGE (q:A3EntityQueue {key:'jobs'}) SET q.lock=coalesce(q.lock,0)+1").consume()
        row=tx.run('''MATCH (s:A3Snapshot) WHERE s.completed=true
          AND s.entity_resolution_requested_at IS NOT NULL
          AND (s.entity_resolution_state='pending' OR
            (s.entity_resolution_state='running' AND s.entity_resolution_lease<timestamp()))
          AND coalesce(s.entity_resolution_attempts,0)<3
          AND NOT EXISTS { MATCH (other:A3Snapshot) WHERE other.company_id=s.company_id
            AND other<>s AND other.entity_resolution_state='running' AND other.entity_resolution_lease>=timestamp() }
          WITH s ORDER BY coalesce(s.entity_resolution_requested_at,0) DESC,s.run_id LIMIT 1
          SET s.entity_resolution_lease=timestamp()+900000,
              s.entity_resolution_attempts=coalesce(s.entity_resolution_attempts,0)+1,
              s.entity_resolution_state='running',s.entity_resolution_claim=$token
          RETURN properties(s) AS scope''',token=token).single()
        return row['scope'] if row else None
    with connection() as session:
        # Idle polls should not acquire a write lock or grow the transaction log.
        if not session.run('''MATCH (s:A3Snapshot) WHERE s.completed=true
          AND s.entity_resolution_requested_at IS NOT NULL
          AND coalesce(s.entity_resolution_attempts,0)<3
          AND (s.entity_resolution_state='pending' OR
              (s.entity_resolution_state='running' AND s.entity_resolution_lease<timestamp()))
          RETURN s.key AS key LIMIT 1''').single():
            return None
        return session.execute_write(write)


def finish_entity_job(scope, result):
    with connection() as session:
        session.run('''MATCH (s:A3Snapshot {key:$key})
          WHERE s.entity_resolution_claim=$token
          SET s.entity_resolution_state=$state, s.entity_resolution_result=$result,
              s.entity_resolution_lease=null''',key=scope['key'],
          state='complete' if result['status']=='complete' else 'failed' if scope.get('entity_resolution_attempts',0)>=3 else 'pending',
          result=json.dumps(result,ensure_ascii=False),token=scope.get('entity_resolution_claim')).consume()


def identity_status(scope):
    with connection() as session:
        row=session.run('''MATCH (s:A3Snapshot {key:$scope.key,completed:true})
            WHERE s.company_id=$scope.company_id AND s.fingerprint=$scope.fingerprint
            RETURN s.entity_resolution_state AS state,s.entity_resolution_attempts AS attempts,
              s.entity_resolution_result AS result''',scope=scope).single()
        if not row:return dict(state='not_ready')
        result=dict(row)
        if result.get('result'):result['result']=json.loads(result['result'])
        return result


def shared_entity_sources(seed_scopes, allowed_scopes, limit=24):
    """Compatibility entry point: document graphs never expand into other documents."""
    return []


def neighbors(scope, seed_ids, limit=None):
    """Hierarchy siblings and source-backed semantic links, never another snapshot."""
    query = '''
    MATCH (s:A3Snapshot {key:$scope.key})
    WHERE s.company_id=$scope.company_id AND s.contract_id=$scope.contract_id
      AND s.version_id=$scope.version_id AND s.run_id=$scope.run_id AND s.fingerprint=$scope.fingerprint
    MATCH (seed:A3Node {snapshot_key:s.key, category:'evidence'})
    WHERE seed.leaf_id IN $seed_ids
    CALL (seed) {
      MATCH (seed)<-[:HAS_EVIDENCE]-(owner)-[link]-(other)-[:HAS_EVIDENCE]->(target:A3Node)
      WHERE owner.snapshot_key=seed.snapshot_key AND other.snapshot_key=seed.snapshot_key
        AND coalesce(owner.kind,'') <> 'document' AND coalesce(other.kind,'') <> 'document'
        AND type(link) <> 'HAS_EVIDENCE'
        AND (type(link) <> 'CONTAINS' OR startNode(link)=owner)
        AND NOT EXISTS {
          MATCH (owner)-[:CONTAINS*1..]->(child)-[:HAS_EVIDENCE]->(seed)
          WHERE child.snapshot_key=seed.snapshot_key AND child.category<>'contract_clause'
        }
      RETURN target, CASE WHEN type(link) IN ['LEFT_OF','ABOVE','NEAR']
        AND EXISTS { MATCH (:A3Node {snapshot_key:seed.snapshot_key,category:'contract_clause'}) }
        THEN 'spatial_candidate' ELSE 'direct_structure_relation' END AS reason
      UNION
      MATCH (seed)-[:MENTIONS]->(entity:A3Node {category:'entity'})<-[:MENTIONS]-(target:A3Node)
      WHERE entity.snapshot_key=seed.snapshot_key AND target.snapshot_key=seed.snapshot_key
      RETURN target, CASE WHEN coalesce(entity.is_party,false) THEN 'shared_party_mention' ELSE 'shared_entity_mention' END AS reason
      UNION
      MATCH (seed)-[:REFERENCES]->(cited:A3Node)<-[:HAS_EVIDENCE]-(clause:A3Node {category:'contract_clause'})-[:HAS_EVIDENCE]->(target:A3Node)
      WHERE cited.snapshot_key=seed.snapshot_key AND clause.snapshot_key=seed.snapshot_key AND target.snapshot_key=seed.snapshot_key
      RETURN target, 'document_reference' AS reason
      UNION
      MATCH (seed)-[:HAS_FIGURE_TEXT|FIGURE_CAPTION_CANDIDATE|FIGURE_NEAR_TEXT_CANDIDATE]->(visual_text:A3Node)-[:MENTIONS]->(entity:A3Node {category:'entity'})<-[:MENTIONS]-(target:A3Node)
      WHERE visual_text.snapshot_key=seed.snapshot_key AND entity.snapshot_key=seed.snapshot_key
        AND target.snapshot_key=seed.snapshot_key
      RETURN target, 'visual_text_shared_entity_candidate' AS reason
      UNION
      MATCH (seed)-[:MENTIONS]->(entity)-[link]-(other)<-[:MENTIONS]-(target:A3Node)
      WHERE type(link) IN $semantic_types AND entity.snapshot_key=seed.snapshot_key
        AND other.snapshot_key=seed.snapshot_key
      RETURN target, 'semantic_relation' AS reason
      UNION
      MATCH (seed)-[document_link]-(target:A3Node)
      WHERE type(document_link) IN $semantic_types
      RETURN target, CASE WHEN type(document_link)='RELATED_PASSAGE'
        THEN 'retrieval_similarity' WHEN type(document_link)='HAS_FIGURE_TEXT'
        THEN 'visual_source_parent' WHEN type(document_link) IN ['FIGURE_CAPTION_CANDIDATE','FIGURE_NEAR_TEXT_CANDIDATE']
        THEN 'visual_caption_candidate' ELSE 'document_reference' END AS reason
      UNION
      MATCH (seed)-[:HAS_FIGURE_TEXT|FIGURE_CAPTION_CANDIDATE|FIGURE_NEAR_TEXT_CANDIDATE]->(visual_text:A3Node)-[:RELATED_PASSAGE]-(target:A3Node)
      WHERE visual_text.snapshot_key=seed.snapshot_key AND target.snapshot_key=seed.snapshot_key
      RETURN target, 'visual_related_passage_candidate' AS reason
      UNION
      MATCH (seed)-[:HAS_VISUAL]->(image)<-[:APPEARS_IN]-(object)<-[:EXPLAINS]-(target:A3Node)
      WHERE image.snapshot_key=seed.snapshot_key AND object.snapshot_key=seed.snapshot_key
      RETURN target, 'visual_explanation' AS reason
      UNION
      MATCH (seed)-[:EXPLAINS]->(object)-[:APPEARS_IN]->(image)<-[:HAS_VISUAL]-(target:A3Node)
      WHERE image.snapshot_key=seed.snapshot_key AND object.snapshot_key=seed.snapshot_key
      RETURN target, 'visual_source' AS reason
    }
    WITH seed, target, reason
    WHERE target.snapshot_key=seed.snapshot_key AND target.category='evidence'
      AND NOT target.leaf_id IN $seed_ids
    RETURN DISTINCT seed.leaf_id AS seed_id, target.leaf_id AS leaf_id, reason
    ORDER BY seed_id, reason, leaf_id
    '''
    if limit is not None:
        query += ' LIMIT $limit'
    with connection() as session:
        return session.execute_read(lambda tx: [dict(row) for row in tx.run(
            query, scope=scope, seed_ids=seed_ids, limit=limit,semantic_types=['RELATED',*SEMANTIC_EDGE_TYPES,*RETRIEVAL_EDGE_TYPES,*VISUAL_SOURCE_EDGE_TYPES])])



def context_edges(scope, leaf_ids, limit=None, seed_ids=None):
    """Read hierarchy and connected relations for supplied current evidence only."""
    query = '''
    MATCH (s:A3Snapshot {key:$scope.key})
    WHERE s.company_id=$scope.company_id AND s.contract_id=$scope.contract_id
      AND s.version_id=$scope.version_id AND s.run_id=$scope.run_id
      AND s.fingerprint=$scope.fingerprint
    MATCH (e:A3Node {snapshot_key:s.key, category:'evidence'})
    WHERE e.leaf_id IN $seed_ids
    CALL (e) {
      MATCH p=(ancestor:A3Node)-[:CONTAINS*0..]->(owner:A3Node)-[:HAS_EVIDENCE]->(e)
      WHERE all(n IN nodes(p) WHERE n.snapshot_key=e.snapshot_key)
      UNWIND relationships(p) AS r RETURN r
      UNION
      MATCH (e)-[r]-(other:A3Node)
      WHERE other.snapshot_key=e.snapshot_key RETURN r
      UNION
      MATCH (e)-[first:MENTIONS]->(entity:A3Node {category:'entity'})<-[second:MENTIONS]-(other:A3Node)
      WHERE entity.snapshot_key=e.snapshot_key AND other.snapshot_key=e.snapshot_key
        AND other.leaf_id IN $leaf_ids
      UNWIND [first,second] AS r RETURN r
      UNION
      MATCH (e)-[visual:HAS_FIGURE_TEXT|FIGURE_CAPTION_CANDIDATE|FIGURE_NEAR_TEXT_CANDIDATE]->(child:A3Node)-[first:MENTIONS]->(entity:A3Node {category:'entity'})<-[second:MENTIONS]-(other:A3Node)
      WHERE child.snapshot_key=e.snapshot_key AND entity.snapshot_key=e.snapshot_key
        AND other.snapshot_key=e.snapshot_key AND child.leaf_id IN $leaf_ids AND other.leaf_id IN $leaf_ids
      UNWIND [visual,first,second] AS r RETURN r
      UNION
      MATCH (e)-[visual:HAS_FIGURE_TEXT|FIGURE_CAPTION_CANDIDATE|FIGURE_NEAR_TEXT_CANDIDATE]->(child:A3Node)-[related:RELATED_PASSAGE]-(target:A3Node)
      WHERE child.snapshot_key=e.snapshot_key AND target.snapshot_key=e.snapshot_key
        AND child.leaf_id IN $leaf_ids AND target.leaf_id IN $leaf_ids
      UNWIND [visual,related] AS r RETURN r
      UNION
      MATCH (table:A3Node)-[:HAS_EVIDENCE]->(e)
      WHERE table.category='table' OR table.kind='table'
      MATCH p=(table)-[:HAS_ROW|HAS_CELL*1..2]->(cell:A3Node)
      WHERE all(n IN nodes(p) WHERE n.snapshot_key=e.snapshot_key)
      UNWIND relationships(p) AS r RETURN r
      UNION
      MATCH (owner:A3Node)-[:HAS_EVIDENCE]->(e)
      MATCH (owner)-[r:HAS_EMBEDDING]->(embedding:A3Node)
      WHERE owner.snapshot_key=e.snapshot_key AND embedding.snapshot_key=e.snapshot_key
      RETURN r
      UNION
      MATCH (e)-[:HAS_VISUAL]->(image)<-[r:APPEARS_IN]-(object:A3Node)
      WHERE image.snapshot_key=e.snapshot_key AND object.snapshot_key=e.snapshot_key
        AND (EXISTS {
          MATCH (object)-[:HAS_EVIDENCE]->(owned:A3Node)
          WHERE owned.snapshot_key=e.snapshot_key AND owned.leaf_id IN $leaf_ids
        } OR EXISTS {
          MATCH (object)<-[:EXPLAINS]-(owned:A3Node)
          WHERE owned.snapshot_key=e.snapshot_key AND owned.leaf_id IN $leaf_ids
        }) RETURN r
      UNION
      MATCH (a:A3Node)-[r]->(b:A3Node)
      WHERE type(r) IN $semantic_types AND a.snapshot_key=e.snapshot_key AND b.snapshot_key=e.snapshot_key
        AND r.source_leaf_id=e.leaf_id RETURN r
      UNION
      MATCH (a:A3Node)-[:HAS_EVIDENCE]->(e)
      MATCH p=(a)-[:LEFT_OF|ABOVE|NEAR|NEXT]-(b:A3Node)-[:HAS_EVIDENCE]->(other:A3Node)
      WHERE a.snapshot_key=e.snapshot_key AND b.snapshot_key=e.snapshot_key
        AND other.snapshot_key=e.snapshot_key AND other.leaf_id IN $leaf_ids
      UNWIND relationships(p) AS r RETURN r
    }
    WITH DISTINCT r
    WITH type(r) AS kind, r
    ORDER BY startNode(r).key, endNode(r).key, coalesce(r.predicate,''), coalesce(r.source_leaf_id,'')
    WITH kind, collect(r) AS batch
    UNWIND range(0, size(batch)-1) AS rank
    WITH batch[rank] AS r, rank
    RETURN startNode(r).key AS from_key, endNode(r).key AS to_key, type(r) AS type,
           coalesce(r.predicate,'') AS predicate, coalesce(r.source_leaf_id,'') AS source_leaf_id,
           r.occurrence_key AS occurrence_key
    ORDER BY rank, CASE WHEN type(r) IN $semantic_types THEN -1 ELSE CASE type(r) WHEN 'CONTAINS' THEN 0 WHEN 'HAS_ROW' THEN 1
             WHEN 'HAS_CELL' THEN 2 WHEN 'HAS_EVIDENCE' THEN 3
             WHEN 'RELATED' THEN 4 WHEN 'MENTIONS' THEN 4 WHEN 'NEXT' THEN 5
             WHEN 'HAS_VISUAL' THEN 6 WHEN 'APPEARS_IN' THEN 6 ELSE 7 END END,
             from_key, to_key, type, predicate, source_leaf_id
    '''
    if limit is not None:
        limit = max(1, int(limit))
        query += ' LIMIT $limit'
    with connection() as session:
        rows = session.execute_read(lambda tx: [dict(row) for row in tx.run(
            query, scope=scope, leaf_ids=list(leaf_ids), seed_ids=list(leaf_ids if seed_ids is None else seed_ids), limit=limit+1 if limit is not None else None,semantic_types=['RELATED',*SEMANTIC_EDGE_TYPES,*RETRIEVAL_EDGE_TYPES,*VISUAL_SOURCE_EDGE_TYPES])])
    return dict(edges=rows if limit is None else rows[:limit], truncated=limit is not None and len(rows)>limit)


def visualization(scope, kinds, page=None, offset=0, limit=60, focus=None):
    """Read a bounded slice of the stored graph, after validating its full scope."""
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    def read(tx):
        snapshot = tx.run('MATCH (s:A3Snapshot {key:$scope.key}) '
                          'WHERE s.company_id=$scope.company_id AND s.contract_id=$scope.contract_id '
                          'AND s.version_id=$scope.version_id AND s.run_id=$scope.run_id '
                          'AND s.fingerprint=$scope.fingerprint RETURN s.key AS key', scope=scope).single()
        if not snapshot:
            return dict(status='not_indexed', nodes=[], edges=[], counts={}, total_nodes=0,
                        total_edges=0, matched_edges=0, offset=offset, limit=limit)
        node_count = tx.run('MATCH (n:A3Node {snapshot_key:$key}) RETURN count(n) AS count',
                            key=scope['key']).single()['count']
        counts = {r['kind']: r['count'] for r in tx.run(
            'MATCH (a:A3Node {snapshot_key:$key})-[r]->(b:A3Node {snapshot_key:$key}) '
            'RETURN type(r) AS kind, count(r) AS count ORDER BY kind', key=scope['key'])}
        # Both endpoints must belong to the selected page. A heading shared
        # by multiple pages must not pull in evidence from other pages.
        def on_page(alias):
            return f'''({alias}.page_number=$page OR ({alias}.page_number IS NULL AND (
              EXISTS {{ MATCH ({alias})-[:HAS_EVIDENCE]->(e:A3Node {{snapshot_key:$key, page_number:$page}}) }}
              OR EXISTS {{ MATCH ({alias})<-[:MENTIONS]-(e:A3Node {{snapshot_key:$key, page_number:$page}}) }}
              OR EXISTS {{ MATCH ({alias})<-[:HAS_CELL|HAS_ROW*1..2]-(owner:A3Node {{snapshot_key:$key}})
                          -[:HAS_EVIDENCE]->(e:A3Node {{snapshot_key:$key, page_number:$page}}) }}
              OR ({alias}.category='structure' AND EXISTS {{
                MATCH ({alias})-[:CONTAINS*1..8]->(owner:A3Node {{snapshot_key:$key}})
                      -[:HAS_EVIDENCE]->(e:A3Node {{snapshot_key:$key, page_number:$page}}) }})
            )))'''
        match = '''MATCH (a:A3Node {snapshot_key:$key})-[r]->(b:A3Node {snapshot_key:$key})
        WHERE type(r) IN $kinds AND ($focus IS NULL OR a.key=$focus OR b.key=$focus)
        AND ($page IS NULL OR ''' + on_page('a') + ' AND ' + on_page('b') + ') '
        params = dict(key=scope['key'], kinds=list(kinds), page=page, offset=offset, limit=limit, focus=focus)
        page_counts, page_nodes = counts, node_count
        if page is not None:
            page_match = 'MATCH (a:A3Node {snapshot_key:$key})-[r]->(b:A3Node {snapshot_key:$key}) WHERE ' + on_page('a') + ' AND ' + on_page('b') + ' '
            page_counts = {r['kind']:r['count'] for r in tx.run(
                page_match+'RETURN type(r) AS kind, count(r) AS count ORDER BY kind', **params)}
            page_nodes = tx.run(page_match+'UNWIND [a,b] AS n RETURN count(DISTINCT n) AS count', **params).single()['count']
        matched = tx.run(match+'RETURN count(r) AS count', **params).single()['count']
        # Round-robin types instead of alphabetical batches: APPEARS_IN must
        # not occupy the entire first page. Each type is ordered deterministically
        # before interleaving, so pagination neither drops nor repeats edges.
        balanced = '''UNWIND range(0, size($kinds)-1) AS kind_index
        WITH kind_index, $kinds[kind_index] AS kind
        CALL (kind) {
        ''' + match.replace('type(r) IN $kinds', 'type(r) = kind') + '''
          WITH a, b, r ORDER BY a.key, b.key LIMIT $fetch_limit
          RETURN collect({a:properties(a), b:properties(b), props:properties(r), kind:type(r)}) AS batch
        }
        UNWIND range(0, size(batch)-1) AS rank
        WITH batch[rank] AS item, rank, kind_index
        ORDER BY rank, kind_index SKIP $offset LIMIT $limit
        RETURN item.a AS a, item.b AS b, item.props AS props, item.kind AS kind
        '''
        rows = list(tx.run(balanced, fetch_limit=min(offset+limit, matched+limit), **params))
        nodes, edges = {}, []
        for row in rows:
            for endpoint in ('a', 'b'):
                n = row[endpoint]
                nodes[n['key']] = n
            edges.append(dict(from_key=row['a']['key'], to_key=row['b']['key'],
                              type=row['kind'], **row['props']))
        return dict(status='ready', nodes=list(nodes.values()), edges=edges, counts=counts,
                    page_counts=page_counts, page_nodes=page_nodes,
                    total_nodes=node_count, total_edges=sum(counts.values()), matched_edges=matched,
                    offset=offset, limit=limit)
    with connection() as session:
        return session.execute_read(read)
