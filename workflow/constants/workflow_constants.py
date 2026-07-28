"""
workflow/constants/workflow_constants.py

All shared literal constants for the Workflow module.
Magic strings and numbers that previously lived inside business logic
are centralised here so they can be updated in a single place.
"""


class RiskLevel:
    """Valid risk level values accepted by every workflow endpoint."""
    LOW = 'LOW'
    MEDIUM = 'MEDIUM'
    HIGH = 'HIGH'

    ALL = {LOW, MEDIUM, HIGH}
    DEFAULT = MEDIUM


class ContractType:
    """Well-known contract type slugs used in branching logic."""
    NDA = 'nda'
    NON_DISCLOSURE = 'non-disclosure'
    PROCUREMENT = 'procurement'
    SERVICE = 'service'
    GENERAL = 'general'

    NDA_TYPES = {NDA, NON_DISCLOSURE}


class WorkflowName:
    """Display names returned inside API responses."""
    ENTERPRISE_HIGH_VALUE = 'Enterprise High-Value Procurement Workflow'
    STANDARD_NDA = 'Standard NDA Approval Workflow'
    ENTERPRISE_PROCUREMENT = 'Enterprise Procurement Workflow'


class Confidence:
    """AI confidence score defaults per workflow branch (0-100)."""
    HIGH_VALUE = 95
    NDA = 92
    DEFAULT = 88


class StepMeta:
    """Canonical step name strings used inside service responses."""
    LEGAL_REVIEW = 'Legal Review'
    COMPLIANCE_CHECK = 'Compliance Check'
    FINANCE_REVIEW = 'Finance Review'
    MANAGER_APPROVAL = 'Manager Approval'
    DIRECTOR_APPROVAL = 'Director Approval'
    CEO_APPROVAL = 'CEO Approval'
    CONTRACT_SIGNING = 'Contract Signing'
    ARCHIVE = 'Archive'

    # Business-rule-triggered optional steps
    NDA_REVIEW = 'NDA Review'
    PRIVACY_ASSESSMENT = 'Privacy Assessment'
    CROSS_BORDER_COMPLIANCE = 'Cross-Border Compliance'

    # Owners
    OWNER_LEGAL = 'Legal Department'
    OWNER_COMPLIANCE = 'Compliance Team'
    OWNER_FINANCE = 'Finance Department'
    OWNER_MANAGER = 'Department Manager'
    OWNER_DIRECTOR = 'Director / VP'
    OWNER_CEO = 'CEO'
    OWNER_SIGNERS = 'Authorized Signers'
    OWNER_SYSTEM = 'System'
    OWNER_DPO = 'Data Protection Officer'

    # Duration defaults (working days)
    DAYS_LEGAL = 2
    DAYS_COMPLIANCE = 2
    DAYS_FINANCE = 1
    DAYS_MANAGER = 1
    DAYS_DIRECTOR = 2
    DAYS_CEO = 1
    DAYS_SIGNING = 1
    DAYS_ARCHIVE = 0
    DAYS_NDA_REVIEW = 1
    DAYS_PRIVACY_ASSESSMENT = 2
    DAYS_CROSS_BORDER = 2


# High-value contract threshold (USD)
HIGH_VALUE_THRESHOLD = 500_000

