"""Link citations between the documents of one company, both ways, every time a document is extracted.

A citation is kept on the passage that writes it ("khoản 2 Điều 17 của Luật Hộ tịch") with the law it names and
the numbers it cites, never with a passage of the other document. When document X finishes extraction:
  outgoing: X's citations are matched to the documents in the library and linked to the cited article or paragraph;
  incoming: every other document's citations are matched against X and linked into X's new passages.
Extracting X again deletes its old passages and every edge touching them; this step then rebuilds both directions,
so a document uploaded before the law it cites gets its link when that law arrives.

The cited law is matched to a document title by the multilingual reranker; a document number written in the
citation ("91/2015/QH13") must agree with the title when both carry one. Articles and paragraphs are matched by the
numbers the citation writes, as within one document.
"""
import logging
import re

logger = logging.getLogger(__name__)

# Measured on 591 citations of 9 KB laws against their titles: the laws themselves scored 1.66 to 5.24 and led the
# next title by 2 or more ("Bộ luật Dân sự" 1.66 vs -0.52); "pháp luật", "Chính phủ", "Tòa án" and laws outside the
# library all scored below 0; "Bộ luật tố tụng dân sự" reached the amending law only 0.64 ahead of the Civil Code.
LAW_MATCH_LOGIT = 1.5
LAW_MATCH_MARGIN = 1.5
DOCUMENT_NUMBER = re.compile(r'\b\d{1,4}/\d{4}/[A-ZĐ0-9-]+\b', re.IGNORECASE)


def library(run):
    """The latest completed run of every other legal text of the same company, with a published graph. Contracts take
    no part in links between documents: a contract is read on its own, and its risk analysis finds the law itself."""
    from ai_extract.repositories import layout_repository
    others = layout_repository.latest_company_runs(run.version.contract.company_id, run.version.contract_id)
    others = [other for other in others if (other.structure or {}).get('graph_index', {}).get('status') == 'ready']
    legal = layout_repository.legal_contract_ids(other.version.contract_id for other in others)
    return [other for other in others if other.version.contract_id in legal]


def citations(run):
    document = ((run.structure or {}).get('knowledge_graph') or {}).get('document_relations') or {}
    return [c for c in document.get('outside_citations', []) if c.get('law')]


def year(title):
    numbers = DOCUMENT_NUMBER.findall(title or '')
    return int(numbers[0].split('/')[1]) if numbers else None


def match_documents(laws, documents, reranker=None, citing_year=None, citing=None):
    """{law text: document} for each cited law the reranker places on one title clearly.
    Versions of one law ("Luật Hộ tịch" 60/2014 and 03/2026) score alike; then the version the citing document
    could cite, the latest issued no later than it, is taken; without a year to compare the citation stays open."""
    from .passage_reference_service import request_rerank
    laws = list(dict.fromkeys(laws))
    # A law naming its own field cites itself, not another version of itself: the 2014 civil status law writes
    # "pháp luật về hộ tịch", and with the law itself out of the candidates the 2026 version won the phrase.
    # A later, different law stays a candidate: a citation of a replaced law applies to the law replacing it.
    if citing is not None:
        documents = [d for d in documents if not _versions_of_one_law([citing, d])]
    if not laws or not documents:
        return {}
    titles = [d.version.contract.title for d in documents]
    scores = (reranker or request_rerank)([[law, title] for law in laws for title in titles])
    matched = {}
    for index, law in enumerate(laws):
        ranked = sorted(zip(scores[index*len(titles):(index+1)*len(titles)], range(len(titles))), reverse=True)
        best, position = ranked[0]
        second = ranked[1][0] if len(ranked) > 1 else float('-inf')
        written = {n.upper() for n in DOCUMENT_NUMBER.findall(law)}
        title_numbers = {n.upper() for n in DOCUMENT_NUMBER.findall(titles[position])}
        if written and title_numbers and not written & title_numbers:
            continue  # "Luật Hộ tịch 60/2014" never lands on the 2026 law
        if best < LAW_MATCH_LOGIT:
            continue
        if best-second >= LAW_MATCH_MARGIN:
            matched[law] = documents[position]
            continue
        contenders = [documents[i] for score, i in ranked if best-score < LAW_MATCH_MARGIN and score >= LAW_MATCH_LOGIT]
        if citing_year is not None and len(contenders) > 1 and _versions_of_one_law(contenders):
            earlier = [d for d in contenders if year(d.version.contract.title) and year(d.version.contract.title) <= citing_year]
            if earlier:
                matched[law] = max(earlier, key=lambda d: year(d.version.contract.title))
    return matched


def _versions_of_one_law(documents):
    """Titles equal once their document numbers are removed: "Luật Hộ tịch số 60/2014/QH13", "... số 03/2026/QH16"."""
    names = {' '.join(DOCUMENT_NUMBER.sub('', d.version.contract.title).replace(' số ', ' ').split()).casefold().removesuffix(' số')
             for d in documents}
    return len(names) == 1


def target_leaves(citation, tree):
    """Passages of the cited document a citation lands on; empty when it names the whole document."""
    from .contract_clause_service import _number_value
    from .passage_reference_service import paragraph_leaf
    clauses = (tree.get('contract_clauses') or {})
    if not citation['articles'] or clauses.get('status') != 'complete':
        return []
    leaves = {leaf['chunk_id']: leaf for leaf in tree.get('leaves', [])}
    numbered = {_number_value(c['title']): c for c in clauses['clauses']}
    found = []
    for article in citation['articles']:
        clause = numbered.get(article)
        if not clause:
            continue
        ids = [i for i in clause['source_ids'] if i in leaves]
        named = [paragraph_leaf(ids, leaves, p) for p in citation.get('paragraphs', [])]
        found.extend([n for n in named if n] or ids[1:2] or ids[:1])
    return list(dict.fromkeys(found))


def links_between(source_run, cited, target_run):
    """Edges from source_run's citations that name target_run."""
    from .document_graph_service import graph_scope
    source_key = graph_scope(source_run, source_run.structure)['key']
    target_key = graph_scope(target_run, target_run.structure)['key']
    edges = []
    for citation in cited:
        targets = target_leaves(citation, target_run.structure)
        for target in targets or [None]:
            edges.append(dict(
                from_key=f'{source_key}:leaf:{citation["source_id"]}',
                to_key=f'{target_key}:leaf:{target}' if target else f'{target_key}:node:root',
                from_run=source_run.pk, to_run=target_run.pk, mention=citation['mention'], law=citation['law'],
                source_leaf_id=citation['source_id'],
                articles=citation['articles'], paragraphs=citation.get('paragraphs', []),
                target_source_leaf_id=target or '', reference_type='references_other_document'
                if target else 'references_whole_document'))
    return edges


def link_documents(run, reranker=None, writer=None, identity=None, deferred_contract_ids=()):
    """Rebuild every citation edge between run and the rest of the library, in both directions, and the
    same-name entities GLiNER2 confirms between them.

    deferred_contract_ids: documents of the same bulk rerun that are still waiting for their turn. Each of them links
    to this one in both directions when it runs, so linking them now would be undone; they are left out of the edges
    and entity pairs, though still counted when deciding which document a citation names, so a law cited by name
    cannot fall to another version of it only because that version waits."""
    from ai_extract.repositories import document_graph_repository as repository
    from ai_extract.repositories import layout_repository
    from .document_graph_service import graph_scope
    if not layout_repository.is_legal_contract(run.version.contract_id):
        # A contract links to no other document; edges left from before this rule are cleared.
        result = (writer or repository.replace_cross_document_links)(graph_scope(run, run.structure)['key'], [])
        summary = dict(status='not_applicable', reason='contract', outgoing=0, incoming=0, documents=0, written=result)
        run.structure['cross_document_links'] = dict(summary, links=[], entity_links=[])
        return summary
    candidates = library(run)
    deferred = set(deferred_contract_ids)
    others = [o for o in candidates if o.version.contract_id not in deferred]
    edges, unresolved = [], []
    # Outgoing: what this document cites.
    own = citations(run)
    matched = match_documents([c['law'] for c in own], candidates, reranker, year(run.version.contract.title), run)
    by_document = {}
    for citation in own:
        target = matched.get(citation['law'])
        if target is None:
            unresolved.append(citation['law'])
        elif target.version.contract_id not in deferred:
            by_document.setdefault(target.pk, (target, []))[1].append(citation)
    for target, cited in by_document.values():
        edges.extend(links_between(run, cited, target))
    # Incoming: what the other documents cite of this one.
    for other in others:
        theirs = citations(other)
        if not theirs:
            continue
        found = match_documents([c['law'] for c in theirs], [run, *[o for o in candidates if o.pk != other.pk]], reranker,
                                year(other.version.contract.title), other)
        cited = [c for c in theirs if found.get(c['law']) is run]
        if cited:
            edges.extend(links_between(other, cited, run))
    # A passage naming one law twice ("Bộ luật dân sự ... Bộ luật dân sự") is one link.
    edges = list({(e['from_key'], e['to_key']): e for e in edges}.values())
    key = graph_scope(run, run.structure)['key']
    result = (writer or repository.replace_cross_document_links)(key, edges)
    summary = dict(status='complete', outgoing=sum(e['from_run'] == run.pk for e in edges),
                   incoming=sum(e['to_run'] == run.pk for e in edges), unresolved_laws=sorted(set(unresolved))[:50],
                   documents=len(others), deferred_documents=len(candidates)-len(others), written=result)
    entity_links, asked = confirm_shared_entities(run, others, identity) if others else ([], 0)
    summary.update(entity_pairs_read=asked, entity_links=len(entity_links))
    run.structure['cross_document_links'] = dict(summary, links=edges, entity_links=entity_links)
    return summary


# Same-name entities across documents, confirmed by GLiNER2 reading both contexts; bounded per extraction.
ENTITY_PAIR_LIMIT = 400


def entity_sides(run):
    """First mention of each entity name in a document, with its source context, as identity pairs need it."""
    from .gliner_identity_classifier import identity_name_key
    sides = {}
    for mention in ((run.structure or {}).get('identity_resolution') or {}).get('source_mentions', []):
        key = identity_name_key(mention['name'])
        if key not in sides and mention.get('context') and mention.get('scope'):
            sides[key] = dict(name=mention['name'], context=mention['context'], scope=dict(mention['scope']))
    return sides


def confirm_shared_entities(run, others, requester=None):
    """Entity names this document shares with each other one that GLiNER2 calls the same thing in both.
    Both passages carry one spelling, so the model compares the contexts, not the letters."""
    import hashlib
    import json
    from .gliner_identity_classifier import IDENTITY_BATCH, renamed, request_identity_pairs
    requester = requester or request_identity_pairs
    mine = entity_sides(run)
    pairs, owners = [], {}
    for other in others:
        theirs = entity_sides(other)
        for key in sorted(set(mine) & set(theirs)):
            left, right = mine[key], theirs[key]
            if right['name'] != left['name']:
                right = renamed(right, left['name'])
            identity = hashlib.sha256(json.dumps([run.pk, other.pk, key], ensure_ascii=False).encode()).hexdigest()
            pairs.append(dict(id=identity, entity_type='ENTITY', left=left, right=right))
            owners[identity] = (other.pk, key)
    pairs = pairs[:ENTITY_PAIR_LIMIT]
    links = []
    for offset in range(0, len(pairs), IDENTITY_BATCH):
        for decision in requester(pairs[offset:offset+IDENTITY_BATCH]).get('decisions', []):
            if decision.get('status') == 'same' and decision['id'] in owners:
                other_pk, key = owners[decision['id']]
                links.append(dict(name_key=key, runs=sorted([run.pk, other_pk])))
    return links, len(pairs)
