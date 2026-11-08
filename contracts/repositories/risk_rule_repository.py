"""The risk rules an administrator sets; the risk analysis files each finding under one of them."""
from contracts.models import RiskRule

OTHER_CODE = 'OTHER'


def active_rules():
    return list(RiskRule.objects.exclude(rule_code=OTHER_CODE).order_by('rule_code'))


def rule_for(code):
    """The rule with this code, or the catch-all rule for a risk no rule describes."""
    rule = RiskRule.objects.filter(rule_code=code).first() if code and code != OTHER_CODE else None
    if rule is not None:
        return rule
    rule, _ = RiskRule.objects.get_or_create(rule_code=OTHER_CODE, defaults=dict(
        rule_name='Rủi ro khác', severity='MEDIUM', description='Rủi ro không thuộc danh mục rủi ro đã đặt sẵn.'))
    return rule
