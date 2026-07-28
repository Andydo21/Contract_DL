"""
workflow/validators/template_validators.py

Validation logic for Workflow Template create and import operations.
"""
from workflow.exceptions import WorkflowValidationException

_REQUIRED_STEP_KEYS = {'step', 'owner', 'estimated_days'}
_REQUIRED_IMPORT_KEYS = {'name', 'steps'}


class TemplateCreateValidator:
    """
    Validates the body for POST /workflow/api/templates/ (create).

    Rules
    -----
    - name          : required, non-empty string.
    - steps         : required, must be a non-empty list.
    - Each step     : must be a dict containing 'step', 'owner',
                      'estimated_days' keys.
    - estimated_days: per step, must be a non-negative integer.
    """

    @staticmethod
    def validate(body: dict) -> None:
        name = body.get('name', '')
        if not isinstance(name, str) or not name.strip():
            raise WorkflowValidationException(
                "Field 'name' is required and must be a non-empty string.",
                code='MISSING_FIELD',
            )

        steps = body.get('steps')
        if not isinstance(steps, list) or len(steps) == 0:
            raise WorkflowValidationException(
                "Field 'steps' must be a non-empty list.",
                code='MISSING_FIELD',
            )

        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                raise WorkflowValidationException(
                    f"Step at index {i} must be a JSON object.",
                    code='INVALID_VALUE',
                )
            missing = _REQUIRED_STEP_KEYS - set(step.keys())
            if missing:
                raise WorkflowValidationException(
                    f"Step at index {i} is missing required keys: {sorted(missing)}.",
                    code='MISSING_FIELD',
                )
            try:
                days = int(step['estimated_days'])
                if days < 0:
                    raise ValueError()
            except (TypeError, ValueError):
                raise WorkflowValidationException(
                    f"Step at index {i}: 'estimated_days' must be a non-negative integer.",
                    code='INVALID_VALUE',
                )


class TemplateImportValidator:
    """
    Validates a JSON payload for POST /workflow/api/templates/import/.

    Rules
    -----
    - name          : required, non-empty string.
    - steps         : required, non-empty list.
    - All step rules from TemplateCreateValidator apply.
    """

    @staticmethod
    def validate(body: dict) -> None:
        missing_keys = _REQUIRED_IMPORT_KEYS - set(body.keys())
        if missing_keys:
            raise WorkflowValidationException(
                f"Import payload is missing required keys: {sorted(missing_keys)}.",
                code='MISSING_FIELD',
            )
        # Re-use step validation from the create validator
        TemplateCreateValidator.validate(body)
