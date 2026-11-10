"""Build one domain's corpus from the vbpl.vn dataset on Hugging Face, as listed in `sources/<domain>.json`."""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import transaction

from legal_kb.parser import parse
from legal_kb.repositories import legal_repository

SOURCES = Path(__file__).resolve().parent.parent / 'sources'
FILES = {name: f'data/{name}.parquet' for name in ('metadata', 'relationships', 'content')}

# vbpl labels an edge from a document to another; True when the document is the one acting.
# Labels whose direction could not be checked against known documents are left out.
LABELS = {
    'Sửa đổi, bổ sung': ('amends', True),
    'Văn bản sửa đổi': ('amends', False),
    'Văn bản bổ sung': ('supplements', False),
    'Văn bản được bổ sung': ('supplements', True),
    'Bãi bỏ': ('repeals', True),
    'Thay thế': ('replaces', True),
    'Văn bản hết hiệu lực': ('ends', True),
    'Văn bản quy định hết hiệu lực': ('ends', False),
    'Văn bản bị hết hiệu lực 1 phần': ('ends_part', True),
    'Văn bản quy định hết hiệu lực 1 phần': ('ends_part', False),
    'Quy định chi tiết, hướng dẫn thi hành': ('guides', True),
    'Văn bản HD, QĐ chi tiết': ('guides', False),
    'Văn bản được HD, QĐ chi tiết': ('guides', True),
    'Hợp nhất': ('consolidates', True),
    'Đính chính': ('corrects', True),
}
APPENDIX_CITED = re.compile(
    r'(tại|theo) Phụ lục|Phụ lục (số )?[IVX\d]+ ban hành kèm theo|ban hành kèm theo (Thông tư|Nghị định) này', re.I)


class CorpusError(Exception):
    pass


def manifest(domain):
    path = SOURCES / f'{domain}.json'
    if not path.exists():
        raise CorpusError(f'No manifest {path.name}; known domains: {", ".join(domains())}')
    return json.loads(path.read_text(encoding='utf-8'))


def domains():
    return sorted(p.stem for p in SOURCES.glob('*.json') if not p.stem.endswith('_eval'))


def data_dir():
    return Path(getattr(settings, 'LEGAL_KB_DATA_DIR', '') or Path(settings.BASE_DIR) / 'media' / 'legal_kb')


def fetch(spec, directory, log=print):
    """Local paths of the dataset files at the manifest's revision, downloaded once."""
    from huggingface_hub import hf_hub_download
    paths = {}
    for name, filename in FILES.items():
        target = Path(directory) / spec['revision'][:12] / filename
        if not target.exists():
            log(f'Downloading {filename} ({spec["dataset"]}@{spec["revision"][:12]})')
            hf_hub_download(spec['dataset'], filename, repo_type='dataset', revision=spec['revision'],
                            local_dir=target.parent.parent)
        paths[name] = target
    return paths


def _rows(path, column, values):
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    return ds.dataset(str(path)).to_table(filter=pc.field(column).isin(sorted(values))).to_pylist()


def _date(value):
    try:
        return datetime.strptime((value or '').strip(), '%d/%m/%Y').date()
    except ValueError:
        return None


def gaps(provisions):
    """Text the source seems to have lost: articles missing from the numbering, or an appendix that is cited but
    absent (vbpl often has appendices only as PDF)."""
    numbers = sorted({int(p.article) for p in provisions if p.article.isdigit()})
    if not numbers:
        return ['Không tách được điều nào.']
    warnings = []
    missing = sorted(set(range(1, numbers[-1] + 1)) - set(numbers))
    if missing:
        warnings.append(f'Thiếu Điều {", ".join(map(str, missing))} trong nội dung nguồn.')
    cited = any(APPENDIX_CITED.search(p.text) for p in provisions)
    if cited and not any(p.article.startswith('Phụ lục') for p in provisions):
        warnings.append('Văn bản dẫn tới phụ lục/danh mục kèm theo nhưng nội dung nguồn không có.')
    return warnings


def _relations(paths, ids):
    """Links touching the corpus, read as (actor, effect, subject) -> vbpl label."""
    edges = _rows(paths['relationships'], 'doc_id', ids) + _rows(paths['relationships'], 'other_doc_id', ids)
    relations = {}
    for edge in edges:
        effect = LABELS.get(edge['relationship'])
        if not effect:
            continue
        actor, subject = (edge['doc_id'], edge['other_doc_id']) if effect[1] else (edge['other_doc_id'], edge['doc_id'])
        relations.setdefault((actor, effect[0], subject), edge['relationship'])
    return relations


def _fields(domain, entry, row):
    """Document fields from vbpl's metadata, where the manifest's own values win."""
    return dict(
        number=row['so_ky_hieu'] or entry['number'],
        title=row['title'] or '',
        doc_type=row['loai_van_ban'] or '',
        issuer=row['co_quan_ban_hanh'] or '',
        issued_on=_date(row['ngay_ban_hanh']),
        effective_from=_date(entry['effective_from']) if 'effective_from' in entry else _date(row['ngay_co_hieu_luc']),
        effective_to=_date(entry['effective_to']) if 'effective_to' in entry else _date(row['ngay_het_hieu_luc']),
        status=entry.get('status') or row['tinh_trang_hieu_luc'] or '',
        status_note=entry.get('status_note', ''),
        gaps=entry.get('gaps', ''),
        note=entry.get('note', ''),
        domain=domain,
    )


def run(domain, directory=None, force=False, log=print):
    spec = manifest(domain)
    paths = fetch(spec, directory or data_dir(), log)
    entries = {d['id']: d for d in spec['documents']}
    ids = set(entries)

    meta = {row['id']: row for row in _rows(paths['metadata'], 'id', ids)}
    missing = ids - set(meta)
    if missing:
        raise CorpusError(f'Not in the dataset: {", ".join(entries[i]["number"] for i in sorted(missing))}')
    relations = _relations(paths, ids)
    others = {i for key in relations for i in (key[0], key[2])} - ids
    if others:
        meta.update({row['id']: row for row in _rows(paths['metadata'], 'id', others)})

    log(f'Reading the text of {len(ids)} documents')
    content = {row['id']: row['content_html'] for row in _rows(paths['content'], 'id', ids)}

    report = {'domain': domain, 'documents': len(ids), 'parsed': 0, 'unchanged': 0, 'removed': 0, 'warnings': {}}
    changed = []
    with transaction.atomic():
        for source_id, entry in entries.items():
            html = content.get(source_id) or ''
            content_hash = hashlib.sha256(html.encode('utf-8')).hexdigest()
            fields = _fields(domain, entry, meta[source_id])
            document = legal_repository.document_by_source(source_id)
            if (document and document.content_hash == content_hash and not force
                    and legal_repository.has_provisions(document)):
                legal_repository.update_document(document, fields)
                report['unchanged'] += 1
                continue
            provisions = parse(html)
            warnings = gaps(provisions) if html else ['Nguồn không có nội dung HTML.']
            document = legal_repository.replace_document(
                source_id, {**fields, 'content_hash': content_hash, 'parse_warnings': warnings}, provisions)
            changed.append(document.pk)
            report['parsed'] += 1
            if warnings:
                report['warnings'][document.number] = warnings

        report['removed'] = legal_repository.remove_documents_except(domain, ids)
        legal_repository.replace_relations(ids, [
            dict(
                actor_source_id=actor, actor_number=meta.get(actor, {}).get('so_ky_hieu') or '',
                actor_title=meta.get(actor, {}).get('title') or '',
                actor_effective_from=_date(meta.get(actor, {}).get('ngay_co_hieu_luc')),
                effect=effect, subject_source_id=subject,
                subject_number=meta.get(subject, {}).get('so_ky_hieu') or '', label=label,
            )
            for (actor, effect, subject), label in relations.items()
        ])
        report['relations'] = len(relations)
        legal_repository.index_documents(changed)
    report['provisions'] = legal_repository.provision_count(domain)
    return report
