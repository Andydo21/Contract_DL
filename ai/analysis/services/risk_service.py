"""The risk rule catalog: the kinds of risk an administrator sets; the risk analysis files each finding under one."""
from ai.analysis.repositories import risk_data_repository as data_repository
from ai.analysis.repositories.risk_repository import RiskRepository
from contract.core.repositories.audit_log_repository import AuditLogRepository
from contract.core.services.results import ServiceResult

SEVERITIES = ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')


def risks_list(method, data):
    """GET: every risk rule with the contracts it was found in. POST: a new risk rule."""
    if method == 'GET':
        return ServiceResult(list_all_risks())
    if method == 'POST':
        try:
            risk = create_new_risk(data.get('risk_name'), data.get('description', ''), data.get('severity_level', 'MEDIUM'))
        except ValueError as error:
            return ServiceResult({'error': str(error)}, status=400)
        return ServiceResult({'success': True, 'risk_id': risk.id, 'risk_name': risk.rule_name, 'severity_level': risk.severity})
    return ServiceResult({'error': 'Method not allowed.'}, status=405)


def list_all_risks():
    result = []
    for rule in RiskRepository.get_all_risks():
        contract_ids = data_repository.distinct_risk_finding_for_list_all_risks(rule)
        contracts = data_repository.only_contract_for_list_all_risks(contract_ids)
        result.append({'id': rule.id, 'risk_name': rule.rule_name, 'risk_code': rule.rule_code,
                       'description': rule.description, 'severity_level': rule.severity,
                       'contracts': [{'id': c.id, 'title': c.title, 'contract_code': c.contract_code} for c in contracts]})
    return result


def create_new_risk(name, description, severity_level):
    if not name:
        raise ValueError('Risk name is required.')
    if severity_level not in SEVERITIES:
        raise ValueError('Invalid severity level. Must be LOW, MEDIUM, HIGH, or CRITICAL.')
    risk = RiskRepository.create_risk(name, description, severity_level)
    AuditLogRepository.log_action(data_repository.first_user_for_create_new_risk(), 'RISK_CREATED', 'Risk', risk.id)
    return risk
