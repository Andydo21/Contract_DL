"""Database operations for analysis workflows."""
from contracts.models import Contract

def get_contract_for_analyze_contract(contract_id):
    return Contract.objects.get(id=contract_id)






