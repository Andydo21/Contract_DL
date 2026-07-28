"""
workflow/exceptions/workflow_exceptions.py

Custom exception hierarchy for the Workflow module.
Raising domain-specific exceptions instead of generic ones
gives callers clearer error handling targets.
"""


class WorkflowBaseException(Exception):
    """
    Base class for all Workflow module exceptions.
    Carries an optional machine-readable ``code`` attribute
    so API error handlers can map exceptions to HTTP status codes
    without inspecting message strings.
    """

    def __init__(self, message: str, code: str = 'WORKFLOW_ERROR'):
        super().__init__(message)
        self.code = code


class WorkflowValidationException(WorkflowBaseException):
    """
    Raised when an incoming request payload fails validation.
    Typically maps to HTTP 400 Bad Request.

    Example::

        raise WorkflowValidationException(
            "Field 'contract_type' is required.",
            code='MISSING_FIELD'
        )
    """

    def __init__(self, message: str, code: str = 'VALIDATION_ERROR'):
        super().__init__(message, code)


class WorkflowServiceException(WorkflowBaseException):
    """
    Raised when a service-layer operation fails (e.g. the future
    AI inference call returns an unexpected payload).
    Typically maps to HTTP 500 Internal Server Error.

    Example::

        raise WorkflowServiceException(
            "AI inference endpoint returned an invalid response."
        )
    """

    def __init__(self, message: str, code: str = 'SERVICE_ERROR'):
        super().__init__(message, code)


class WorkflowConfigurationException(WorkflowBaseException):
    """
    Raised when the module is misconfigured (e.g. a required
    environment variable or settings key is missing).
    Typically logged as a critical error and maps to HTTP 503.

    Example::

        raise WorkflowConfigurationException(
            "AI_SERVICE_URL is not set in Django settings."
        )
    """

    def __init__(self, message: str, code: str = 'CONFIGURATION_ERROR'):
        super().__init__(message, code)
