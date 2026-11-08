"""Mark stored documents as legal, or take the mark away; extract them again so articles are recognised."""
from django.core.management.base import BaseCommand, CommandError
from contracts.models import Contract
from NewIdea.repositories import knowledge_repository


class Command(BaseCommand):
    help = 'Mark contracts by code as legal documents.'

    def add_arguments(self, parser):
        parser.add_argument('codes', nargs='+')
        parser.add_argument('--unmark', action='store_true')

    def handle(self, *args, **options):
        contracts = list(Contract.objects.filter(contract_code__in=options['codes']))
        missing = set(options['codes'])-{contract.contract_code for contract in contracts}
        if missing:
            raise CommandError(f'Unknown contract codes: {", ".join(sorted(missing))}')
        for contract in contracts:
            if options['unmark']:
                knowledge_repository.unmark_legal(contract)
            else:
                knowledge_repository.mark_legal(contract)
            self.stdout.write(f'{contract.contract_code}: {"unmarked" if options["unmark"] else "marked"}')
