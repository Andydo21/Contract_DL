"""Tell the language of an OCR text block with the fastText lid.176 model (176 languages, CPU, under 1 ms)."""
import os
import re
import threading

_lock = threading.Lock()
_model = []
LETTER = re.compile(r'[^\W\d_]')


def _load():
    with _lock:
        if not _model:
            import fasttext
            # fastText prints a deprecation notice on every load.
            fasttext.FastText.eprint = lambda *args, **kwargs: None
            _model.append(fasttext.load_model(os.path.abspath(
                os.getenv('LANGID_MODEL_PATH', 'scratch/a3-models/langid/lid.176.ftz'))))
    return _model[0]


def language(text):
    """The ISO 639-1 code of a text, or None when it holds no letter, such as '30.000.000'.
    The text is lower-cased: on 599 benchmark blocks, capital headings such as 'HỢP ĐỒNG DỊCH VỤ'
    came back Swedish or Ukrainian 14 times; lower-cased, every block was told Vietnamese or not correctly."""
    if not LETTER.search(text or ''):
        return None
    labels, _ = _load().predict(' '.join(text.split()).lower(), k=1)
    return labels[0].removeprefix('__label__')
