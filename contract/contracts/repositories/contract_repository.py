from contract.contracts.models import Contract


class ContractRepository:
    @staticmethod
    def get_all_contracts():
        return Contract.objects.all().order_by('-created_at')
        
    @staticmethod
    def get_contracts_by_company(company):
        return Contract.objects.filter(company=company).order_by('-created_at')
        
    @staticmethod
    def get_contract(contract_id):
        """The contract alone, without its versions and analyses; None when it does not exist (or is deleted)."""
        return Contract.objects.filter(pk=contract_id).first()

    @staticmethod
    def lock_contract(contract_id):
        """The contract, locked until the transaction ends, so two writers number versions one after the other."""
        return Contract.objects.select_for_update().filter(pk=contract_id).first()

    @staticmethod
    def get_contract_by_id(contract_id):
        try:
            return Contract.objects.prefetch_related(
                'versions__files',
                'versions__ai_extract_clauses', 
                'versions__ai_analyses__findings__rule', 
                'versions__ai_analyses__reviews__user'
            ).get(id=contract_id)
        except Contract.DoesNotExist:
            return None
            
    @staticmethod
    def create_contract(code, title, contract_type, start_date, end_date, contract_value, status='DRAFT', company=None):
        return Contract.objects.create(
            contract_code=code,
            title=title,
            contract_type=contract_type,
            start_date=start_date,
            end_date=end_date,
            contract_value=contract_value,
            status=status,
            company=company
        )

    @staticmethod
    def update_contract(contract, fields):
        for name, value in fields.items():
            setattr(contract, name, value)
        contract.save(update_fields=[*fields, 'updated_at'])
        return contract

    @staticmethod
    def soft_delete_contract(contract, user):
        from django.utils import timezone
        contract.deleted_at = timezone.now()
        contract.deleted_by = user if user and user.is_authenticated else None
        contract.save(update_fields=['deleted_at', 'deleted_by', 'updated_at'])
        return contract

    @staticmethod
    def deleted_contracts(company_id=None):
        """The trash: deleted contracts, newest first; of one company, or of every company when company_id is None."""
        rows = Contract.all_objects.filter(deleted_at__isnull=False).select_related('deleted_by').order_by('-deleted_at')
        return rows if company_id is None else rows.filter(company_id=company_id)

    @staticmethod
    def codes_in_use(contracts):
        """(company id, code) pairs among the given contracts that a live contract of the same company uses now."""
        contracts = list(contracts)
        rows = Contract.objects.filter(contract_code__in={c.contract_code for c in contracts},
                                       company_id__in={c.company_id for c in contracts if c.company_id}) \
            | Contract.objects.filter(contract_code__in={c.contract_code for c in contracts if not c.company_id},
                                      company__isnull=True)
        return set(rows.values_list('company_id', 'contract_code'))

    @staticmethod
    def deleted_contract(contract_id):
        return Contract.all_objects.filter(pk=contract_id, deleted_at__isnull=False).first()

    @staticmethod
    def restore_contracts(queryset):
        """Bring deleted contracts back. Returns (contracts restored, contracts left deleted because another
        contract of the same company uses their code now)."""
        deleted = list(queryset.filter(deleted_at__isnull=False).order_by('-deleted_at'))
        used = ContractRepository.codes_in_use(deleted)
        restored, blocked = [], []
        for contract in deleted:
            key = (contract.company_id, contract.contract_code)
            if key in used:
                blocked.append(contract)
                continue
            Contract.all_objects.filter(pk=contract.pk).update(deleted_at=None, deleted_by=None)
            used.add(key)
            restored.append(contract)
        return restored, blocked
