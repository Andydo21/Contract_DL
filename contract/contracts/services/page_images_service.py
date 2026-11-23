"""Join the photos of one document, taken page by page, into a single PDF in the order the user set.

The PDF then follows the main extraction flow page by page (orientation, OCR, clauses), so photos need no
separate path. A phone writes the camera turn into EXIF instead of the pixels; that turn is applied here,
because a PDF page keeps no EXIF. Sideways or upside-down pages are turned later by the page orientation model.
"""
import io
from pathlib import Path

from django.core.files.base import ContentFile

IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'}
MAX_PAGES = 100
MAX_IMAGE_BYTES = 25*1024*1024
MAX_PIXELS = 50_000_000
# Each photo becomes a page whose longer side is A4's (11.69 in); the 150 and 300 dpi renders then hold
# about 1,750 and 3,500 pixels on that side, as a scanned page would.
A4_LONG_INCHES = 11.69


class PageImagesError(ValueError):
    pass


def is_image(upload):
    return Path(upload.name or '').suffix.lower() in IMAGE_SUFFIXES


def images_to_pdf(uploads):
    """uploads in page order; returns a ContentFile holding a PDF with one page per photo."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    if not uploads:
        raise PageImagesError('Chưa có ảnh nào.')
    if len(uploads) > MAX_PAGES:
        raise PageImagesError(f'Tối đa {MAX_PAGES} ảnh cho một văn bản.')
    pages = []
    try:
        for number, upload in enumerate(uploads, 1):
            if not is_image(upload):
                raise PageImagesError(f'Trang {number} ({upload.name}) không phải ảnh. Khi gửi nhiều file, mọi file phải là ảnh.')
            if upload.size > MAX_IMAGE_BYTES:
                raise PageImagesError(f'Trang {number} ({upload.name}) vượt quá {MAX_IMAGE_BYTES//(1024*1024)} MB.')
            data = upload.read()
            try:
                with Image.open(io.BytesIO(data)) as probe:
                    probe.verify()
                image = Image.open(io.BytesIO(data))
                if image.width*image.height > MAX_PIXELS:
                    raise PageImagesError(f'Trang {number} ({upload.name}) có độ phân giải quá lớn.')
                page = ImageOps.exif_transpose(image).convert('RGB')
            except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as error:
                raise PageImagesError(f'Trang {number} ({upload.name}) không đọc được: {type(error).__name__}.') from error
            pages.append(page)
        buffer = io.BytesIO()
        resolution = max(max(page.size) for page in pages)/A4_LONG_INCHES
        # Pillow stores RGB pages as JPEG; its default quality blurs small print.
        pages[0].save(buffer, format='PDF', save_all=True, append_images=pages[1:], resolution=resolution, quality=92)
    finally:
        for page in pages:
            page.close()
    stem = Path(uploads[0].name or 'anh').stem
    return ContentFile(buffer.getvalue(), name=f'{stem}_{len(uploads)}_trang.pdf')


# What a single uploaded document may be, and the bytes each kind starts with: a renamed .exe or a truncated
# download is refused at the door instead of failing later inside the extraction.
DOCUMENT_SIGNATURES = {'.pdf': (b'%PDF',), '.docx': (b'PK\x03\x04',), '.doc': (b'\xd0\xcf\x11\xe0',), '.txt': ()}
MAX_TEXT_CHARS = 2_000_000


def max_document_bytes():
    from django.conf import settings
    return int(getattr(settings, 'CONTRACT_UPLOAD_MAX_MB', 50))*1024*1024


def check_document(upload):
    """Refuse a single file that is too large, of a kind the pipeline does not read, or not what its name says."""
    suffix = Path(upload.name or '').suffix.lower()
    if suffix not in DOCUMENT_SIGNATURES and suffix not in IMAGE_SUFFIXES:
        raise PageImagesError(f'Không nhận loại file "{suffix or upload.name}". Hãy tải PDF, DOCX, DOC, TXT hoặc ảnh.')
    limit = max_document_bytes()
    if upload.size is not None and upload.size > limit:
        raise PageImagesError(f'File {upload.name} vượt quá {limit//(1024*1024)} MB.')
    if not upload.size:
        raise PageImagesError(f'File {upload.name} rỗng.')
    head = upload.read(2048)
    upload.seek(0)
    if suffix in IMAGE_SUFFIXES:
        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(upload) as probe:
                probe.verify()
        except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as error:
            raise PageImagesError(f'File {upload.name} không phải ảnh đọc được.') from error
        finally:
            upload.seek(0)
        return upload
    signatures = DOCUMENT_SIGNATURES[suffix]
    # A PDF may carry a few junk bytes before its header; readers accept it within the first kilobyte.
    if signatures and not any(head.startswith(s) or (suffix == '.pdf' and s in head[:1024]) for s in signatures):
        raise PageImagesError(f'Nội dung file {upload.name} không phải {suffix.lstrip(".").upper()}.')
    if suffix == '.txt' and b'\x00' in head:
        raise PageImagesError(f'File {upload.name} không phải văn bản thuần.')
    return upload


def check_raw_content(text):
    if text and len(text) > MAX_TEXT_CHARS:
        raise PageImagesError(f'Nội dung dán vào dài quá {MAX_TEXT_CHARS:,} ký tự; hãy tải file thay vì dán.'.replace(',', '.'))


def document_upload(uploads):
    """The one file to store for an upload: a single file as it is (checked), several photos joined into a PDF."""
    files = list(uploads.getlist('file')) if hasattr(uploads, 'getlist') else [f for f in [uploads.get('file')] if f]
    if len(files) <= 1:
        return check_document(files[0]) if files else None
    return images_to_pdf(files)
