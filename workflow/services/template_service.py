"""
workflow/services/template_service.py

In-memory mock store for Workflow Templates.
A module-level dict acts as the runtime data store — data persists for
the lifetime of the Django process and resets on server restart, which
is intentional for this mock phase.
"""
import copy
import uuid
from datetime import datetime

from workflow.exceptions import WorkflowServiceException, WorkflowValidationException


# ─────────────────────────────────────────────────────────────────────────────
# Seed data — 7 reusable mock templates
# ─────────────────────────────────────────────────────────────────────────────

_SEED_TEMPLATES = [
    {
        'id': 'tpl-service-agreement',
        'name': 'Service Agreement',
        'description': 'Standard workflow for reviewing and approving service-level agreements with external vendors and partners.',
        'category': 'Service',
        'departments_involved': ['Legal Department', 'Finance Department', 'Department Manager'],
        'total_estimated_days': 8,
        'last_updated': '2026-07-20',
        'is_custom': False,
        'steps': [
            {'step': 'Legal Review',      'owner': 'Legal Department',   'estimated_days': 2, 'priority': 'high'},
            {'step': 'Finance Review',    'owner': 'Finance Department', 'estimated_days': 1, 'priority': 'medium'},
            {'step': 'Manager Approval',  'owner': 'Department Manager', 'estimated_days': 1, 'priority': 'medium'},
            {'step': 'Director Approval', 'owner': 'Director / VP',      'estimated_days': 2, 'priority': 'high'},
            {'step': 'Contract Signing',  'owner': 'Authorized Signers', 'estimated_days': 1, 'priority': 'high'},
            {'step': 'Archive',           'owner': 'System',             'estimated_days': 0, 'priority': 'low'},
        ],
    },
    {
        'id': 'tpl-employment-contract',
        'name': 'Employment Contract',
        'description': 'HR-driven workflow for processing employment agreements, including legal and HR sign-off stages.',
        'category': 'HR',
        'departments_involved': ['Legal Department', 'HR Department', 'Department Manager'],
        'total_estimated_days': 6,
        'last_updated': '2026-07-18',
        'is_custom': False,
        'steps': [
            {'step': 'Legal Review',     'owner': 'Legal Department',   'estimated_days': 2, 'priority': 'high'},
            {'step': 'HR Review',        'owner': 'HR Department',      'estimated_days': 1, 'priority': 'medium'},
            {'step': 'Manager Approval', 'owner': 'Department Manager', 'estimated_days': 1, 'priority': 'medium'},
            {'step': 'Contract Signing', 'owner': 'Authorized Signers', 'estimated_days': 1, 'priority': 'high'},
            {'step': 'Archive',          'owner': 'System',             'estimated_days': 0, 'priority': 'low'},
        ],
    },
    {
        'id': 'tpl-nda',
        'name': 'Non-Disclosure Agreement',
        'description': 'Fast-track NDA workflow for standard confidentiality agreements with minimal approval layers.',
        'category': 'Legal',
        'departments_involved': ['Legal Department', 'Department Manager'],
        'total_estimated_days': 4,
        'last_updated': '2026-07-25',
        'is_custom': False,
        'steps': [
            {'step': 'Legal Review',     'owner': 'Legal Department',   'estimated_days': 2, 'priority': 'high'},
            {'step': 'Manager Approval', 'owner': 'Department Manager', 'estimated_days': 1, 'priority': 'medium'},
            {'step': 'Contract Signing', 'owner': 'Authorized Signers', 'estimated_days': 1, 'priority': 'high'},
            {'step': 'Archive',          'owner': 'System',             'estimated_days': 0, 'priority': 'low'},
        ],
    },
    {
        'id': 'tpl-vendor-approval',
        'name': 'Vendor Approval',
        'description': 'Enterprise vendor onboarding workflow including compliance checks, finance review, and executive sign-off.',
        'category': 'Procurement',
        'departments_involved': ['Legal Department', 'Compliance Team', 'Finance Department', 'CEO'],
        'total_estimated_days': 11,
        'last_updated': '2026-07-15',
        'is_custom': False,
        'steps': [
            {'step': 'Legal Review',      'owner': 'Legal Department',   'estimated_days': 2, 'priority': 'high'},
            {'step': 'Compliance Check',  'owner': 'Compliance Team',    'estimated_days': 2, 'priority': 'high'},
            {'step': 'Finance Review',    'owner': 'Finance Department', 'estimated_days': 1, 'priority': 'medium'},
            {'step': 'Manager Approval',  'owner': 'Department Manager', 'estimated_days': 1, 'priority': 'medium'},
            {'step': 'Director Approval', 'owner': 'Director / VP',      'estimated_days': 2, 'priority': 'high'},
            {'step': 'CEO Approval',      'owner': 'CEO',                'estimated_days': 1, 'priority': 'critical'},
            {'step': 'Contract Signing',  'owner': 'Authorized Signers', 'estimated_days': 1, 'priority': 'high'},
            {'step': 'Archive',           'owner': 'System',             'estimated_days': 0, 'priority': 'low'},
        ],
    },
    {
        'id': 'tpl-software-license',
        'name': 'Software License',
        'description': 'Streamlined workflow for software licensing agreements covering IP, legal, and finance approvals.',
        'category': 'Technology',
        'departments_involved': ['Legal Department', 'IT Department', 'Finance Department'],
        'total_estimated_days': 6,
        'last_updated': '2026-07-22',
        'is_custom': False,
        'steps': [
            {'step': 'Legal Review',     'owner': 'Legal Department',   'estimated_days': 2, 'priority': 'high'},
            {'step': 'IT Review',        'owner': 'IT Department',      'estimated_days': 1, 'priority': 'medium'},
            {'step': 'Finance Review',   'owner': 'Finance Department', 'estimated_days': 1, 'priority': 'medium'},
            {'step': 'Manager Approval', 'owner': 'Department Manager', 'estimated_days': 1, 'priority': 'medium'},
            {'step': 'Contract Signing', 'owner': 'Authorized Signers', 'estimated_days': 1, 'priority': 'high'},
            {'step': 'Archive',          'owner': 'System',             'estimated_days': 0, 'priority': 'low'},
        ],
    },
    {
        'id': 'tpl-procurement',
        'name': 'Procurement Contract',
        'description': 'High-value procurement workflow with full compliance, finance, and executive approval chain.',
        'category': 'Procurement',
        'departments_involved': ['Legal Department', 'Compliance Team', 'Finance Department', 'Director / VP'],
        'total_estimated_days': 10,
        'last_updated': '2026-07-10',
        'is_custom': False,
        'steps': [
            {'step': 'Legal Review',      'owner': 'Legal Department',   'estimated_days': 2, 'priority': 'high'},
            {'step': 'Compliance Check',  'owner': 'Compliance Team',    'estimated_days': 2, 'priority': 'high'},
            {'step': 'Finance Review',    'owner': 'Finance Department', 'estimated_days': 1, 'priority': 'medium'},
            {'step': 'Manager Approval',  'owner': 'Department Manager', 'estimated_days': 1, 'priority': 'medium'},
            {'step': 'Director Approval', 'owner': 'Director / VP',      'estimated_days': 2, 'priority': 'high'},
            {'step': 'Contract Signing',  'owner': 'Authorized Signers', 'estimated_days': 1, 'priority': 'high'},
            {'step': 'Archive',           'owner': 'System',             'estimated_days': 0, 'priority': 'low'},
        ],
    },
    {
        'id': 'tpl-custom-workflow',
        'name': 'Custom Workflow',
        'description': 'A flexible template with minimal steps that you can customise to match any business process.',
        'category': 'Custom',
        'departments_involved': ['Department Manager'],
        'total_estimated_days': 3,
        'last_updated': '2026-07-27',
        'is_custom': True,
        'steps': [
            {'step': 'Manager Approval',  'owner': 'Department Manager', 'estimated_days': 1, 'priority': 'medium'},
            {'step': 'Contract Signing',  'owner': 'Authorized Signers', 'estimated_days': 1, 'priority': 'high'},
            {'step': 'Archive',           'owner': 'System',             'estimated_days': 0, 'priority': 'low'},
        ],
    },
]

# Runtime store — keyed by template id.
_STORE: dict = {t['id']: copy.deepcopy(t) for t in _SEED_TEMPLATES}


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────

class WorkflowTemplateService:
    """
    CRUD-like service over the in-memory template store.

    All mutations return the affected template (or a list of templates)
    so that views can serialise the result directly as JSON.
    """

    # ── Read ──────────────────────────────────────────────────────────────

    def list_templates(self) -> list:
        """Return all templates as a list of dicts (copies to avoid mutation)."""
        return [copy.deepcopy(t) for t in _STORE.values()]

    def get_template(self, template_id: str) -> dict:
        """
        Return a single template by id.

        Raises:
            WorkflowServiceException: if not found.
        """
        template = _STORE.get(template_id)
        if not template:
            raise WorkflowServiceException(
                f"Template '{template_id}' not found.",
                code='NOT_FOUND',
            )
        return copy.deepcopy(template)

    # ── Create ────────────────────────────────────────────────────────────

    def create_template(self, data: dict) -> dict:
        """
        Create a new custom template from validated data.

        Args:
            data: dict with keys name, description, category,
                  departments_involved (list), steps (list of step dicts).

        Returns:
            The newly created template dict.
        """
        try:
            new_id = f"tpl-custom-{uuid.uuid4().hex[:8]}"
            steps = data.get('steps', [])
            total_days = sum(
                int(s.get('estimated_days', 1)) for s in steps
                if str(s.get('estimated_days', 1)).isdigit()
            )
            template = {
                'id': new_id,
                'name': str(data['name']).strip(),
                'description': str(data.get('description', '')).strip(),
                'category': str(data.get('category', 'Custom')).strip(),
                'departments_involved': data.get('departments_involved', []),
                'total_estimated_days': total_days,
                'last_updated': datetime.today().strftime('%Y-%m-%d'),
                'is_custom': True,
                'steps': steps,
            }
            _STORE[new_id] = copy.deepcopy(template)
            return copy.deepcopy(template)
        except Exception as exc:
            raise WorkflowServiceException(
                f"Failed to create template: {exc}"
            ) from exc

    # ── Duplicate ─────────────────────────────────────────────────────────

    def duplicate_template(self, template_id: str) -> dict:
        """
        Clone an existing template with a new id and '(Copy)' suffix.

        Returns:
            The cloned template dict.

        Raises:
            WorkflowServiceException: if source template not found.
        """
        source = self.get_template(template_id)
        new_id = f"tpl-copy-{uuid.uuid4().hex[:8]}"
        clone = copy.deepcopy(source)
        clone['id'] = new_id
        clone['name'] = f"{source['name']} (Copy)"
        clone['is_custom'] = True
        clone['last_updated'] = datetime.today().strftime('%Y-%m-%d')
        _STORE[new_id] = copy.deepcopy(clone)
        return copy.deepcopy(clone)

    # ── Import ────────────────────────────────────────────────────────────

    def import_template(self, data: dict) -> dict:
        """
        Import an externally supplied template dict.
        Assigns a new id to avoid conflicts.

        Returns:
            The imported template dict.
        """
        try:
            new_id = f"tpl-import-{uuid.uuid4().hex[:8]}"
            steps = data.get('steps', [])
            total_days = sum(
                int(s.get('estimated_days', 1)) for s in steps
                if str(s.get('estimated_days', '1')).isdigit()
            )
            template = {
                'id': new_id,
                'name': str(data.get('name', 'Imported Workflow')).strip(),
                'description': str(data.get('description', '')).strip(),
                'category': str(data.get('category', 'Imported')).strip(),
                'departments_involved': data.get('departments_involved', []),
                'total_estimated_days': total_days,
                'last_updated': datetime.today().strftime('%Y-%m-%d'),
                'is_custom': True,
                'steps': steps,
            }
            _STORE[new_id] = copy.deepcopy(template)
            return copy.deepcopy(template)
        except Exception as exc:
            raise WorkflowServiceException(
                f"Failed to import template: {exc}"
            ) from exc

    # ── Delete ────────────────────────────────────────────────────────────

    def delete_template(self, template_id: str) -> None:
        """
        Remove a template from the store.

        Raises:
            WorkflowServiceException: if not found.
            WorkflowValidationException: if attempting to delete a built-in template.
        """
        template = _STORE.get(template_id)
        if not template:
            raise WorkflowServiceException(
                f"Template '{template_id}' not found.",
                code='NOT_FOUND',
            )
        if not template.get('is_custom', False):
            raise WorkflowValidationException(
                "Built-in templates cannot be deleted. Duplicate them first.",
                code='FORBIDDEN',
            )
        del _STORE[template_id]
