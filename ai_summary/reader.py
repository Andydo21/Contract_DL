"""Text from uploaded contract files (PDF, DOCX, TXT), read here so summaries never depend on another
extraction service. PDF pages without a text layer (scans) are OCR'd with Tesseract when it is installed."""
import io
import logging
import os
import shutil
import threading
import zipfile
from pathlib import Path

logger = logging.getLogger('ai_summary')

MAX_BYTES = int(os.getenv('SUMMARY_MAX_FILE_MB', '25')) * 1024 * 1024
# A PDF page with fewer extracted characters than this is treated as a scanned image.
MIN_PAGE_CHARS = 40
MAX_OCR_PAGES = int(os.getenv('SUMMARY_MAX_OCR_PAGES', '60'))
OCR_LANGUAGES = os.getenv('SUMMARY_OCR_LANGUAGES', 'vie+eng')
OCR_DPI = 300
_PDF_LOCK = threading.Lock()
# Characters a TCVN3/VNI text layer produces instead of Vietnamese letters, and that Vietnamese text never uses.
LEGACY_MARKS = set('¸µ¶·¹¨¾»¼½Æ©Ç®ÏÑª«¬¯ñæçëïîäåöûüþ÷øßðÞ')
GARBLED_RATIO = 0.02
# Deleted text, drawing fallbacks (they repeat the text box) and properties are not visible text.
DOCX_SKIPPED = {'del', 'moveFrom', 'Fallback', 'pPr', 'rPr', 'instrText', 'delText'}


class ReadError(ValueError):
    """The file cannot be turned into text; the message is shown to the user as is."""


def ocr_available():
    return shutil.which('tesseract') is not None


def read(data: bytes, filename: str = '') -> dict:
    """{'text', 'kind', 'pages', 'ocr_pages', 'unreadable_pages', 'chars', 'warnings'} for one file."""
    if not data:
        raise ReadError('File rỗng.')
    if len(data) > MAX_BYTES:
        raise ReadError(f'File lớn hơn {MAX_BYTES // 1024 // 1024} MB.')
    extension = Path(filename).suffix.lower()
    # The content decides the format: stored names may carry another extension or none.
    if data.startswith(b'%PDF'):
        result = _pdf(data)
    elif data.startswith(b'PK') and _is_docx(data):
        result = _docx(data)
    elif data.startswith(b'\xd0\xcf\x11\xe0') or extension == '.doc':
        raise ReadError('File Word cũ (.doc) chưa được hỗ trợ; hãy lưu lại thành .docx hoặc PDF rồi tải lên.')
    else:
        result = _txt(data)
    result['text'] = result['text'].strip()
    result['chars'] = len(result['text'])
    if result['kind'] != 'pdf' and looks_garbled(result['text']):
        result['warnings'].append('Văn bản có vẻ dùng bảng mã cũ (TCVN3/VNI) nên chữ có thể sai; nên chuyển sang Unicode.')
    if not result['text']:
        raise ReadError('Không đọc được chữ nào từ file' + (
            ' (PDF dạng ảnh scan và máy chủ chưa cài OCR).' if result['unreadable_pages'] else '.'))
    return result


def _result(kind, text, pages=None, ocr_pages=(), unreadable_pages=(), warnings=()):
    return dict(text=text, kind=kind, pages=pages, ocr_pages=list(ocr_pages),
                unreadable_pages=list(unreadable_pages), warnings=list(warnings))


def _is_docx(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return 'word/document.xml' in archive.namelist()
    except zipfile.BadZipFile:
        return False


def looks_garbled(text):
    """Text layers in legacy Vietnamese encodings (TCVN3, VNI) or broken fonts extract as symbols, not words."""
    visible = [c for c in text if not c.isspace()]
    if len(visible) < 20:
        return False
    odd = sum(c in LEGACY_MARKS or c == '\ufffd' or 0xE000 <= ord(c) <= 0xF8FF for c in visible) + 3 * text.count('(cid:')
    return odd >= 5 and odd / len(visible) >= GARBLED_RATIO


def _pdf(data):
    import pymupdf

    with _PDF_LOCK:  # MuPDF is not thread-safe and FastAPI serves requests from a thread pool
        try:
            document = pymupdf.open(stream=data, filetype='pdf')
        except Exception as error:
            raise ReadError(f'PDF hỏng hoặc không mở được: {error}') from error
        try:
            return _read_pdf(document)
        finally:
            document.close()


def _read_pdf(document):
    if document.needs_pass:
        raise ReadError('PDF có mật khẩu; hãy gỡ mật khẩu rồi tải lên lại.')
    can_ocr = ocr_available()
    texts, ocr_pages, unreadable, garbled, warnings = [], [], [], [], []
    skipped_ocr = False
    for number, page in enumerate(document, start=1):
        # sort=True follows the visual reading order, which matters for two-column layouts.
        text = page.get_text('text', sort=True)
        bad_layer = looks_garbled(text)
        if len(text.strip()) < MIN_PAGE_CHARS or bad_layer:
            has_ink = bad_layer or bool(text.strip() or page.get_images() or page.get_drawings())
            if has_ink:  # a truly blank page has nothing to OCR and is not a problem
                ocr_text = ''
                if can_ocr and len(ocr_pages) < MAX_OCR_PAGES:
                    ocr_text = _ocr_page(page)
                elif can_ocr:
                    skipped_ocr = True
                if ocr_text.strip() and (bad_layer or len(ocr_text.strip()) > len(text.strip())):
                    text = ocr_text
                    ocr_pages.append(number)
                elif bad_layer:
                    garbled.append(number)
                elif not text.strip():
                    unreadable.append(number)
        texts.append(text.strip())
    if unreadable:
        warnings.append(f'{len(unreadable)} trang là ảnh scan nhưng không OCR được'
                        + ('' if can_ocr else ' (máy chủ chưa cài Tesseract)') + f': {_ranges(unreadable)}.')
    if garbled:
        warnings.append(f'{len(garbled)} trang dùng font mã cũ (TCVN3/VNI) nên chữ có thể sai: {_ranges(garbled)}.')
    if skipped_ocr:
        warnings.append(f'Chỉ OCR {MAX_OCR_PAGES} trang đầu cần OCR; các trang sau có thể bị thiếu.')
    return _result('pdf', '\n\n'.join(t for t in texts if t), document.page_count, ocr_pages, unreadable, warnings)


def _ocr_page(page):
    try:
        textpage = page.get_textpage_ocr(language=OCR_LANGUAGES, dpi=OCR_DPI, full=True)
        return page.get_text('text', textpage=textpage, sort=True)
    except Exception as error:
        logger.warning('OCR failed on page %s: %s', page.number + 1, error)
        return ''


def _xml_text(element):
    """Visible text of a paragraph from the XML: python-docx's Paragraph.text misses tracked insertions and text boxes."""
    parts = []
    for child in element:
        tag = child.tag.rsplit('}', 1)[-1] if isinstance(child.tag, str) else ''
        if tag == 't':
            parts.append(child.text or '')
        elif tag == 'tab':
            parts.append('\t')
        elif tag in ('br', 'cr'):
            parts.append('\n')
        elif tag == 'p':  # paragraph inside a text box
            parts.append('\n' + _xml_text(child))
        elif tag not in DOCX_SKIPPED:
            parts.append(_xml_text(child))
    return ''.join(parts)


def _docx_blocks(parent):
    """Paragraphs and tables in document order, also inside content controls (w:sdt)."""
    lines = []
    for child in parent:
        tag = child.tag.rsplit('}', 1)[-1] if isinstance(child.tag, str) else ''
        if tag == 'p':
            lines.append(_xml_text(child))
        elif tag == 'tbl':
            lines += _docx_table(child)
        elif tag in ('sdt', 'sdtContent', 'customXml', 'ins', 'smartTag'):
            lines += _docx_blocks(child)
    return lines


def _docx_table(table):
    lines = []
    for row in _children(table, 'tr', 'sdt', 'sdtContent'):
        cells = []
        for cell in _children(row, 'tc', 'sdt', 'sdtContent'):
            value = ' '.join(' '.join(_docx_blocks(cell)).split())
            if value and (not cells or cells[-1] != value):
                cells.append(value)
        if cells:
            lines.append(' | '.join(cells))
    return lines


def _children(element, *tags):
    """Direct children with these tags, looking through content-control wrappers."""
    found = []
    for child in element:
        tag = child.tag.rsplit('}', 1)[-1] if isinstance(child.tag, str) else ''
        if tag in ('sdt', 'sdtContent') and tag in tags:
            found += _children(child, *tags)
        elif tag in tags:
            found.append(child)
    return found


def _docx(data):
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as error:
        raise ReadError(f'DOCX hỏng hoặc không mở được: {error}') from error
    return _result('docx', '\n'.join(line.rstrip() for line in _docx_blocks(document.element.body)))


def _txt(data):
    encoding = 'utf-16' if data[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig'
    try:
        return _result('txt', data.decode(encoding))
    except UnicodeDecodeError:
        pass
    if b'\x00' in data[:4096]:
        raise ReadError('Định dạng file chưa được hỗ trợ; hãy dùng PDF, DOCX hoặc TXT.')
    return _result('txt', data.decode('cp1258', errors='replace'), warnings=['File text không phải UTF-8; đã đọc theo bảng mã Windows-1258.'])


def _ranges(numbers):
    """[1, 2, 3, 7] -> '1-3, 7'."""
    spans, start = [], None
    for index, number in enumerate(numbers):
        if start is None:
            start = number
        if index + 1 == len(numbers) or numbers[index + 1] != number + 1:
            spans.append(f'{start}-{number}' if number != start else str(number))
            start = None
    return ', '.join(spans)
