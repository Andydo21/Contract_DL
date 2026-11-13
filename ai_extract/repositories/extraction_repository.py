"""Contract-version selection and clause access for extraction workflows."""
from contracts.models import Contract, ContractVersion
from ai_extract.models import Clause
from NewIdea.repositories.contract_repository import visible_contracts


def contract_for(user, contract_id):
    return visible_contracts(user).prefetch_related('versions__ai_extract_clauses').get(pk=contract_id)


def visible_contract_rows(user):
    return list(visible_contracts(user).values('id', 'contract_code', 'title', 'end_date'))


def version_for(contract, version_id=None):
    return contract.versions.get(pk=version_id) if version_id else contract.latest_version


def clause_for(user, clause_id):
    return Clause.objects.select_related('version__contract').get(pk=clause_id, version__contract__in=visible_contracts(user))


def clauses_for_version(version):
    return list(Clause.objects.filter(version=version))


def lock_version(version):
    return ContractVersion.objects.select_for_update().get(pk=version.pk)


def delete_version_clauses(version):
    return version.ai_extract_clauses.all().delete()


def replace_contract_clauses(version, clauses, parties, party_types):
    """Replace one version's clauses; the parties the clause step read are stored on the opening clause.
    The clauses' GLiNER entities follow once the headings are settled (replace_clause_entities)."""
    from django.db import transaction
    from ai_extract.models import ExtractedEntity
    with transaction.atomic():
        lock_version(version)
        delete_version_clauses(version)
        saved = [Clause.objects.create(version=version, clause_type=item['clause_type'],
                                       clause_title=item['title'], clause_content=item['content'])
                 for item in clauses]
        for party in parties:
            ExtractedEntity.objects.create(clause=saved[0], entity_type=party_types[party['role']],
                                           entity_value=party['name'], normalized_value=party['name'],
                                           confidence_score=round(party['confidence'], 2))
    return saved


def replace_clause_entities(version, clauses, entities):
    """Store each GLiNER entity under the clause whose passages it was read from: one row per name per clause,
    next to the parties' rows.
    Clauses are matched to the stored rows as in update_clause_contents. Returns rows written, or None when the
    stored clauses no longer match the tree."""
    from django.db import transaction
    from ai_extract.models import ExtractedEntity
    rows = list(Clause.objects.filter(version=version).order_by('pk'))
    if len(rows) != len(clauses) or any(row.clause_title != item['title'] for row, item in zip(rows, clauses)):
        return None
    owner = {}
    for row, item in zip(rows, clauses):
        for source in item.get('source_ids', []):
            owner.setdefault(source, []).append((row, ' '.join(str(item.get('content') or '').split())))
    found = {}
    for entity in entities:
        name = ' '.join(str(entity.get('name') or '').split())
        if not name:
            continue
        key = entity.get('identity_name_key') or name.casefold()
        for source in entity.get('source_ids') or [entity.get('source_id')]:
            # A block split between clauses belongs to the one whose words hold the name.
            candidates = owner.get(source, [])
            for row in [row for row, words in candidates if len(candidates) == 1 or name in words]:
                current = found.get((row.pk, key))
                if current is None or entity.get('confidence', 0) > current.confidence_score:
                    found[(row.pk, key)] = ExtractedEntity(clause=row, entity_type=entity.get('entity_type') or 'ENTITY',
                                                           entity_value=name[:2000], normalized_value=key,
                                                           confidence_score=round(float(entity.get('confidence') or 0), 2))
    with transaction.atomic():
        # The parties' rows came with the clauses and stay.
        ExtractedEntity.objects.filter(clause__version=version).exclude(entity_type__startswith='PARTY').delete()
        ExtractedEntity.objects.bulk_create(found.values())
    return len(found)


def is_legal_document(version):
    from ai_extract.models import LegalDocument
    return LegalDocument.objects.filter(contract_id=version.contract_id).exists()


def update_clause_contents(version, clauses):
    """Bring the stored clauses' text up to the extraction tree in place (the heading step trims the heading lines of
    the next group from an article's end); rows keep their ids, so risk findings stay linked. Clauses are matched in
    order and by title; a list that no longer matches is left for the next clause split. Returns rows updated."""
    rows = list(Clause.objects.filter(version=version).order_by('pk'))
    if len(rows) != len(clauses) or any(row.clause_title != item['title'] for row, item in zip(rows, clauses)):
        return 0
    changed = []
    for row, item in zip(rows, clauses):
        if row.clause_content != item['content']:
            row.clause_content = item['content']
            changed.append(row)
    Clause.objects.bulk_update(changed, ['clause_content'])
    return len(changed)
