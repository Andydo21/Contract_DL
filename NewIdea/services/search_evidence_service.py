"""Build source-bound A2 expert citations and discover indexed structure nodes."""
from urllib.parse import urlencode
from copy import deepcopy
import math
from django.conf import settings
from ai_extract.services.document_graph_service import graph_scope
from shared.retrieval import evidence_identity, lexical_search, tokens
from .case_rules import CASE_FIELDS, serialize_case
from .evidence_service import evidence_current


def find_expert_cases(query, cases, limit=3):
    """Rank approved cases only while their saved evidence is still current."""
    records = [
        dict(case=case, text=' '.join(getattr(case, field) for field in CASE_FIELDS),
             original_name=case.title)
        for case in cases if evidence_current(case)
    ]
    return [
        dict(serialize_case(hit['case']), match_score=hit['lexical_score'],
             requires_applicability_review=True, score_kind='bm25_not_applicability')
        for hit in lexical_search(query, records, limit=limit)
    ]


def select_retrieval_seeds(candidates, limit=None):
    """Cover requested parts, then balance ranked relevance and marginal information.

    Ranks are produced by the existing retrieval/reranker, never inferred from
    document language or domain. Similar passages are downranked, not discarded:
    different versions, quantities, conditions and provenance remain available.
    """
    limit = limit if limit is not None else getattr(settings, 'A2_ANSWER_SOURCE_LIMIT', 24)
    # Keep legacy callers' order when they have no cross-query ranking metadata.
    if not any(c.get('retrieval_ranks') for c in candidates):
        return candidates[:limit]
    remaining = list(range(len(candidates)))
    selected, covered, documents = [], set(), set()
    words, parts, relevance, fusion, docs = [], [], [], [], []
    for index, source in enumerate(candidates):
        words.append(set(tokens(source.get('text', ''))))
        parts.append({h['part'] for h in source.get('retrieval_hints', [])})
        ranks = [h['rank'] for h in source.get('retrieval_ranks', [])] or [index+1]
        relevance.append(max(1 / (1 + math.log2(rank)) for rank in ranks))
        fusion.append(sum(1 / (60 + rank) for rank in ranks))
        docs.append(source.get('document_id') or source.get('version_id'))
    overlap = [0.] * len(candidates)
    while remaining and len(selected) < limit:
        # Coverage first; novelty adjusts relevance without equal document quotas.
        chosen = max(remaining, key=lambda i: (len(parts[i] - covered),
            relevance[i] - 0.35 * overlap[i] + (0.05 if docs[i] not in documents else 0), fusion[i]))
        remaining.remove(chosen)
        selected.append(candidates[chosen])
        covered.update(parts[chosen]); documents.add(docs[chosen])
        for i in remaining:
            overlap[i] = max(overlap[i], len(words[i] & words[chosen]) / max(1, len(words[i] | words[chosen])))
    return selected


def select_answer_sources(candidates, limit=None):
    """Bound ranked seeds, preserving all source context of admitted seeds."""
    limit = limit if limit is not None else getattr(settings, 'A2_ANSWER_SOURCE_LIMIT', 24)
    matches, context, seen, text_seen = [], [], {}, {}
    for contextual in (False, True):
        for source in candidates:
            identity = evidence_identity(source)
            version = source.get('document_id') or source.get('version_id')
            text_key = (version, source.get('source_role'), source.get('evidence_kind'),
                        tuple(source.get('heading_path',[])),
                        ' '.join(source.get('text', '').split()) or identity)
            is_context = source.get('expansion_reason', 'query_match') != 'query_match'
            if is_context != contextual:
                continue
            previous = seen.get(identity) or text_seen.get(text_key)
            if previous is not None:
                for key in ('retrieval_hints', 'retrieval_ranks'):
                    if source.get(key):
                        hints = previous.setdefault(key, [])
                        hints.extend(h for h in source[key] if h not in hints)
                continue
            source = dict(source)
            for key in ('retrieval_hints', 'retrieval_ranks'):
                if key in source:
                    source[key] = list(source[key])
            (context if contextual else matches).append(source)
            seen[identity] = text_seen[text_key] = source
    selected = matches[:limit]
    represented = {s.get('document_id') or s.get('version_id') for s in selected}
    selected.extend(s for s in context
                    if (s.get('document_id') or s.get('version_id')) in represented)
    return [dict(source, evidence_id=f'E{index}') for index, source in enumerate(selected, 1)]


EXPERT_INSTRUCTION = ('Distinguish document facts from approved expert opinions. '
    'Expert cases are conditional advice, not facts established by the source document. State their author, '
    'revision and applicability; do not assume they apply to the current document. '
    'Never omit an expert case applicability condition or its verification limits. '
    'Cases marked DEMO are illustrative sample answers, not real expert testimony '
    'or validated operating procedures; explicitly identify them as demo advice. '
    'Expert units marked draft are unreviewed user submissions, not approved procedures. '
    'Expert questions describe what someone asked, never evidence that its premise is true. '
    'State the author and review status when citing expert submissions; preserve conditions.')


def attach_document_checks(citations, checks):
    """Give each drift pair actual authorized source citations before generation."""
    evidence, checks = [dict(c) for c in citations], deepcopy(checks)
    by_source = {(c.get('version_id'), c.get('source_chunk_id') or c.get('chunk_id')): c for c in evidence
                 if c.get('evidence_kind') != 'expert_opinion'}
    for warning in checks.get('warnings', []):
        warning['document_evidence_ids'] = [c['evidence_id'] for c in evidence
            if c.get('version_id') in (warning['left_version_id'], warning['right_version_id'])
            and c.get('evidence_kind') != 'expert_opinion']
        for difference in warning.get('differences', []):
            for side in ('left', 'right'):
                spec = difference[side]
                source = spec['source']
                key = (source.get('version_id'), source['source_id'])
                citation = by_source.get(key)
                if citation is None:
                    citation = dict(source, evidence_id=f'E{len(evidence)+1}',
                        chunk_id=source['source_id'], source_chunk_id=source['source_id'],
                        evidence_kind='document', heading_path=[], layout_type='paragraph')
                    evidence.append(citation); by_source[key] = citation
                citation['comparison_evidence'] = True
                # Preserve the whole source block so a query window cannot
                # drop the exact compared value or its part number.
                citation['text'] = source['text']
                spec['evidence_id'] = citation['evidence_id']
    return evidence, checks


def with_expert_evidence(citations, cases):
    evidence = [dict(c, evidence_kind=c.get('evidence_kind', 'document')) for c in citations]
    for case in cases[:3]:
        snapshot = case.get('evidence_snapshot') or {}
        if case.get('status') != 'approved' or not snapshot.get('sha256') or not snapshot.get('text'):
            continue
        identifier = f'E{len(evidence)+1}'
        # Full conditions remain intact, rather than keyword-windowing advice.
        text = '\n'.join(f'{label}: {case.get(field, "")}' for label, field in (
            ('Issue', 'issue'), ('Reasoning', 'reasoning'), ('Resolution', 'resolution'),
            ('Verification', 'verification'), ('Applicability', 'applicability')))
        text += '\nSupporting source: '+snapshot['text']
        if case.get('is_demo'):
            text = 'Provenance: DEMO sample answer, checked against document text only.\n' + text
        evidence.append(dict(evidence_id=identifier, evidence_kind='expert_opinion',
            is_demo=case.get('is_demo', False),
            chunk_id=case['evidence_id'], expert_case_id=case['case_id'], revision=case['revision'],
            author=case['author'], reviewer=case.get('reviewer'), applicability=case.get('applicability', ''),
            requires_applicability_review=True, text=text, original_name='Ý kiến chuyên gia: '+case['title'],
            contract_id=case['contract_id'], version_id=case['version_id'],
            source_location=f"{case['author']} · revision {case['revision']} · "+snapshot.get('source_location', ''),
            source_url=snapshot.get('source_url', ''), heading_path=[],
            source_chunk_id=snapshot['chunk_id']))
    return evidence


def matched_structure_nodes(tree, citations, version, run=None):
    """Node lookup through authorized retrieved leaves, not unscoped graph names."""
    by_id = {n['id']: n for n in tree.get('nodes', [])}
    matches = {}
    scope = graph_scope(run, tree) if run and tree.get('graph_index', {}).get('status') == 'ready' else None
    if scope and tree['graph_index'].get('fingerprint') != scope['fingerprint']:
        scope = None
    for citation in citations:
        if citation.get('evidence_kind') == 'expert_opinion':
            continue
        source_identity = 'leaf:'+citation.get('chunk_id', '')
        source_node = dict(node_id=source_identity, title=citation.get('text', '')[:100] or 'Vùng ảnh',
            kind=citation.get('layout_type', 'evidence'), contract_id=version.contract_id, version_id=version.pk,
            evidence_ids=[citation.get('evidence_id')], retrieval_basis='retrieved_source_leaf',
            vector_unit='source_leaf', vector_index_status=getattr(run, 'dense_index_status', 'NOT_INDEXED'),
            source_url=citation.get('source_url', ''))
        if scope:
            params = urlencode(dict(version_id=version.pk, graph_node=scope['key']+':'+source_identity))
            source_node['graph_url'] = f'/ai-extract/contracts/{version.contract_id}/pages/{citation.get("page_number", 1)}/?{params}#neo4j-graph'
        matches.setdefault(source_identity, source_node)
        for identity in citation.get('ancestor_ids', []):
            node = by_id.get(identity)
            if not node or node.get('kind') == 'document':
                continue
            item = matches.setdefault(identity, dict(node_id=identity, title=node['title'], kind=node['kind'],
                contract_id=version.contract_id, version_id=version.pk, evidence_ids=[],
                retrieval_basis='retrieved_leaf_ancestor', independently_vectorized=False,
                source_url=citation.get('source_url', '')))
            if citation.get('evidence_id') not in item['evidence_ids']:
                item['evidence_ids'].append(citation.get('evidence_id'))
            if scope:
                page = citation.get('page_number', 1)
                params = urlencode(dict(version_id=version.pk, graph_node=scope['key']+':node:'+identity))
                item['graph_url'] = f'/ai-extract/contracts/{version.contract_id}/pages/{page}/?{params}#neo4j-graph'
    return list(matches.values())[:30]
