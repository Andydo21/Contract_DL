"""Limits on the summary endpoints a signed-in user can reach directly: input size, how often one account may start a
model call, and who may bypass the cache (force). Every route that can reach the model checks here first."""
from django.conf import settings

from contract.core.services import rate_limit_service
from contract.core.services.access_service import is_manager


class GuardError(Exception):
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


def max_upload_bytes():
    return int(getattr(settings, 'AI_SUMMARY_MAX_UPLOAD_MB', 25)) * 1024 * 1024


def check(user, *, force=False, texts=(), uploads=(), model_call=True):
    """texts: strings the request carries; uploads: uploaded files (anything with .size and .name).
    model_call: whether the request may call the model (and so counts against the per-minute budget)."""
    limit = int(getattr(settings, 'AI_SUMMARY_MAX_TEXT_CHARS', 500_000))
    for text in texts:
        if isinstance(text, str) and len(text) > limit:
            raise GuardError(f'Văn bản dài quá {limit:,} ký tự.'.replace(',', '.'), 413)
    cap = max_upload_bytes()
    for upload in uploads:
        if upload is not None and (upload.size or 0) > cap:
            raise GuardError(f'File {upload.name} vượt quá {cap // (1024 * 1024)} MB.', 413)
    if force and not is_manager(user):
        # force skips the cache and runs the model again; a viewer reads the summary that is there.
        raise GuardError('Chỉ quản lý mới chạy lại được bản tóm tắt (force).', 403)
    if model_call:
        try:
            rate_limit_service.check(user, 'summary', int(getattr(settings, 'AI_SUMMARY_RATE_PER_MINUTE', 10)))
        except rate_limit_service.RateLimited as error:
            raise GuardError(str(error), 429) from error
