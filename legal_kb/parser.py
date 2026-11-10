"""Split the HTML body of a vbpl.vn document into articles and clauses.

vbpl marks its structure with `prov-chapter`, `prov-section`, `prov-article`, `prov-clause` and `prov-item`
classes; documents without them are split on the text itself ("Điều 5.", "1.", "a)"). One `Provision` is a clause
with its points, or the text of an article before its first clause; tables become rows of cells joined with " | ".
"""
import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser

ARTICLE = re.compile(r'^Điều\s+(\d+[a-zđ]?)\s*[.:]\s*(.*)$', re.S)
CLAUSE = re.compile(r'^(\d+[a-zđ]?)\.\s')
POINT = re.compile(r'^([a-zđ]{1,2}\d?)\)\s')
CHAPTER = re.compile(r'^(Chương|Phần thứ|PHẦN THỨ|Phần|PHẦN)\s+\S+', re.I)
SECTION = re.compile(r'^Mục\s+\d+', re.I)
APPENDIX = re.compile(r'^PHỤ\s*LỤC\b')
SIGNATURE = re.compile(
    r'^(Nơi nhận|TM\.|KT\.|Q\. ?BỘ TRƯỞNG|BỘ TRƯỞNG$|CHỦ TỊCH QUỐC HỘI$'
    r'|(Bộ luật|Luật|Nghị quyết|Pháp lệnh) này (đã )?được Quốc hội.{0,80}thông qua)'
)

BLOCK_TAGS = {'p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
APPENDIX_CHUNK = 2500


@dataclass
class Provision:
    article: str  # "21", or "Phụ lục I" for an appendix
    clause: str = ''  # "" for the article's own text before clause 1
    heading: str = ''  # article title
    chapter: str = ''
    section: str = ''
    lines: list = field(default_factory=list)

    @property
    def text(self):
        return '\n'.join(self.lines).strip()

    @property
    def ref(self):
        return ref(self.article, self.clause)


def ref(article, clause):
    """How a provision is cited; a long appendix is stored in numbered parts."""
    if article.startswith('Phụ lục'):
        return article if clause in ('', '1') else f'{article} (phần {clause})'
    return f'Khoản {clause} Điều {article}' if clause else f'Điều {article}'


class _Blocks(HTMLParser):
    """Collect (css class, text) per paragraph; a table row becomes one block with its cells joined."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.text = []
        self.cls = ''
        self.table_depth = 0
        self.cells = []
        self.skip = 0

    def flush(self):
        # A <br> splits a paragraph ("Chương IV<br>TIỀN LƯƠNG"); the parts keep the paragraph's class.
        for line in ''.join(self.text).split('\n'):
            text = _clean(line)
            if text:
                self.blocks.append((self.cls, text))
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
        elif tag == 'br':
            self.text.append(' ' if self.table_depth else '\n')
        elif tag == 'table':
            self.flush()
            self.table_depth += 1
        elif self.table_depth:
            if tag == 'tr':
                self.cells = []
            elif tag == 'p':
                self.cls = self.cls or dict(attrs).get('class') or ''
            elif tag in BLOCK_TAGS:
                self.text.append(' ')
        elif tag in BLOCK_TAGS:
            self.flush()
            self.cls = dict(attrs).get('class') or '' if tag == 'p' else ''

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)
        elif tag == 'table':
            self.table_depth = max(0, self.table_depth - 1)
            self.cls = ''
        elif self.table_depth:
            if tag in ('td', 'th'):
                self.cells.append(_clean(''.join(self.text)))
                self.text = []
            elif tag == 'tr':
                cells = [c for c in self.cells if c]
                if cells:
                    self.blocks.append(('table-row', ' | '.join(cells)))
                self.cells = []
        elif tag in BLOCK_TAGS:
            self.flush()
            self.cls = ''

    def handle_data(self, data):
        if not self.skip:
            self.text.append(data)

    def close(self):
        super().close()
        self.flush()
        return self.blocks


def _clean(text):
    text = unicodedata.normalize('NFC', text.replace('\xa0', ' ').replace('​', ''))
    return re.sub(r'\s+', ' ', text).strip()


def html_blocks(html):
    parser = _Blocks()
    parser.feed(html or '')
    return parser.close()


def _kind(cls, text, tagged):
    """What a block is. Tagged documents are trusted, except that the text must still look like what the tag says."""
    if cls == 'table-row':
        return 'content'
    if APPENDIX.match(text):
        return 'appendix'
    if tagged:
        if ARTICLE.match(text) and 'prov-article' not in cls and len(text) < 300:
            return 'article'  # vbpl sometimes tags an article heading as a clause
        for kind in ('chapter', 'section', 'article', 'clause', 'item'):
            if f'prov-{kind}' in cls:
                if kind == 'article' and not ARTICLE.match(text):
                    return 'content'
                if kind == 'clause' and not CLAUSE.match(text):
                    return 'content'
                return 'point' if kind == 'item' else kind
        return 'content'
    if ARTICLE.match(text):
        return 'article'
    if CLAUSE.match(text):
        return 'clause'
    if POINT.match(text):
        return 'point'
    if SECTION.match(text):
        return 'section'
    if CHAPTER.match(text) and len(text) < 40:
        return 'chapter'
    return 'content'


def parse(html):
    """Provisions of one document, in document order. Text before the first article is left out."""
    blocks = html_blocks(html)
    tagged = any('prov-article' in cls for cls, _ in blocks)
    provisions = []
    chapter = section = ''
    article = None  # (number, heading)
    current = None
    in_appendix = False
    signed = False
    prev_kind = ''

    def start(clause):
        nonlocal current
        current = Provision(article[0], clause, article[1], chapter, section)
        provisions.append(current)
        return current

    for cls, text in blocks:
        kind = _kind(cls, text, tagged)
        if kind == 'content' and prev_kind in ('chapter', 'section') and text.isupper() and len(text) < 200:
            kind = prev_kind  # the title line under "Chương I" / "Mục 1"
        if kind == 'appendix':
            in_appendix, signed = True, False
            article = (_appendix_name(text, provisions), '')
            chapter = section = ''
            start('1').lines.append(text)
            prev_kind = kind
            continue
        if in_appendix:
            if current is not None and sum(map(len, current.lines)) > APPENDIX_CHUNK:
                start(str(int(current.clause) + 1))
            current.lines.append(text)
            continue
        if article is not None and SIGNATURE.match(text):
            signed = True
        if signed:
            continue

        if kind == 'chapter':
            # A chapter number and its title come as two paragraphs.
            chapter = f'{chapter} {text}' if prev_kind == 'chapter' else text
            section = ''
        elif kind == 'section':
            section = f'{section} {text}' if prev_kind == 'section' else text
        elif kind == 'article':
            number, heading = ARTICLE.match(text).groups()
            article = (number, heading.strip())
            current = None
        elif article is None:
            pass
        elif kind == 'clause':
            start(CLAUSE.match(text).group(1)).lines.append(text)
        elif current is None:
            start('').lines.append(text)
        else:
            current.lines.append(text)
        prev_kind = kind

    return [p for p in provisions if p.text or not p.clause]


def _appendix_name(text, provisions):
    match = re.match(r'^PHỤ\s*LỤC\s*(?:SỐ\s*)?([IVXLC]+|\d+[a-z]?)\b', text)
    if match:
        return f'Phụ lục {match.group(1)}'
    count = len({p.article for p in provisions if p.article.startswith('Phụ lục')})
    return f'Phụ lục {count + 1}' if count else 'Phụ lục'


def fold(text):
    """Lower case without Vietnamese diacritics, so "luong toi thieu" finds "lương tối thiểu"."""
    text = unicodedata.normalize('NFD', text.lower()).replace('đ', 'd')
    return unicodedata.normalize('NFC', ''.join(c for c in text if unicodedata.category(c) != 'Mn'))
