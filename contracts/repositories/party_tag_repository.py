"""Contract parties the user enters and the tags an administrator defines."""
from django.db import transaction
from contracts.models import ContractParty, Tag


def parties_of(contract):
    return list(ContractParty.objects.filter(contract=contract).order_by('pk'))


def replace_parties(contract, rows):
    """The parties as the user last entered them, in that order."""
    with transaction.atomic():
        ContractParty.objects.filter(contract=contract).delete()
        return [ContractParty.objects.create(contract=contract, **row) for row in rows]


def all_tags():
    return list(Tag.objects.order_by('tag_name'))


def tags_of(contract):
    return list(contract.tags.order_by('tag_name'))


def set_tags(contract, tag_ids):
    """Only tags an administrator created can be attached."""
    tags = list(Tag.objects.filter(pk__in=tag_ids))
    contract.tags.set(tags)
    return tags
