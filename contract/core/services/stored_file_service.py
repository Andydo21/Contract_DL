"""Where an uploaded contract file lives on disk, and what it contains.

ContractFile.file_path holds the URL the storage gave the file: MEDIA_URL followed by the percent-encoded name, so
"Hợp đồng.pdf" is stored as "/media/contracts/H%E1%BB%A3p_%C4%91%E1%BB%93ng.pdf". The name must be unquoted before it
names a file on disk. Every reader of stored files goes through physical_path() so none of them forgets it."""
import urllib.parse
from pathlib import Path

from django.conf import settings


def physical_path(file_path):
    """The file on disk for a stored URL or storage-relative name; None when it would fall outside MEDIA_ROOT."""
    root = Path(settings.MEDIA_ROOT).resolve()
    relative = urllib.parse.unquote(file_path or '').lstrip('/\\')
    media = settings.MEDIA_URL.strip('/\\')
    if media and relative.startswith(media + '/'):
        relative = relative[len(media) + 1:]
    path = (root / relative).resolve()
    return path if path.is_relative_to(root) else None


def read_decrypted(file_path):
    """The decrypted bytes of a stored file, or None when it is missing or cannot be decrypted."""
    from contract.core.services.document_encryption_service import decrypt_pdf
    path = physical_path(file_path)
    if path is None or not path.is_file():
        return None
    try:
        return decrypt_pdf(path.read_bytes())
    except Exception:
        return None


def file_name_of(file_path):
    """The readable name of a stored file ("Hợp_đồng.pdf", not its percent-encoded URL form)."""
    return Path(urllib.parse.unquote(file_path or '')).name


def document_text(contract_file):
    """The plain text of a stored document: a .txt file decoded, the text layer of a PDF; '' for any other kind of
    file or when it cannot be read."""
    if not contract_file or not contract_file.file_path:
        return ''
    data = read_decrypted(contract_file.file_path)
    if data is None:
        return ''
    name = (contract_file.file_name or file_name_of(contract_file.file_path)).lower()
    if data.startswith(b'%PDF'):
        import fitz
        try:
            with fitz.open(stream=data, filetype='pdf') as pdf:
                return '\n\n'.join(page.get_text() for page in pdf)
        except Exception:
            return ''
    return data.decode('utf-8', errors='ignore') if name.endswith('.txt') else ''
