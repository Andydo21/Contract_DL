"""Turn a page upright before it is stored and read.

docTR's page orientation model (MobileNetV3 small, 6 MB, CPU) tells whether a page lies at 0, 90, 180
or 270 degrees. On the 38 benchmark pages, scans and bilingual pages included, each turned all four ways,
it named all 152 correctly at 72 ms a page, the least sure answer at .94.
"""
import base64
import io
import os
import threading

MODEL_ID = 'doctr-mobilenet_v3_small_page_orientation-8e60325c'
MIN_CONFIDENCE = .9
# The model looks at the page at 512 pixels; a smaller copy is enough to send.
SEND_SIZE = 1024
ANGLES = {0, 90, 180, 270}
_lock = threading.Lock()
_model = []


def _load():
    with _lock:
        if not _model:
            import torch
            from doctr.models import page_orientation_predictor
            predictor = page_orientation_predictor(pretrained=False)
            path = os.getenv('PAGE_ORIENTATION_MODEL_PATH',
                             'scratch/a3-models/doctr/mobilenet_v3_small_page_orientation-8e60325c.pt')
            # The checkpoint is downloaded; load tensors only, never pickled code.
            predictor.model.load_state_dict(torch.load(os.path.abspath(path), map_location='cpu', weights_only=True))
            predictor.model.eval()
            _model.append(predictor)
    return _model[0]


def infer(image):
    """Runtime side: the counter-clockwise turn that puts the page upright."""
    import numpy as np
    predictor = _load()
    with _lock:
        _, angles, confidences = predictor([np.asarray(image.convert('RGB'))])
    return dict(angle=int(angles[0]) % 360, confidence=float(confidences[0]), model=MODEL_ID)


def detect(image):
    from django.conf import settings
    url = getattr(settings, 'RAG_INFERENCE_URL', '')
    if not url:
        return infer(image)
    import requests
    from .contract_pipeline_service import NGROK_HEADERS
    small = image.copy()
    small.thumbnail((SEND_SIZE, SEND_SIZE))
    buffer = io.BytesIO()
    small.save(buffer, format='PNG')
    response = requests.post(url.rstrip('/')+'/rag/page_orientation', headers=NGROK_HEADERS, timeout=(5, 120),
                             json=dict(image_base64=base64.b64encode(buffer.getvalue()).decode('ascii')))
    response.raise_for_status()
    result = response.json()
    if result.get('model') != MODEL_ID or result.get('angle') not in ANGLES:
        raise ValueError('Page orientation runtime is outdated or invalid')
    return result


def upright(image, *companions):
    """Turn the page and its sharper copies by the angle the model names; an unsure answer leaves them.
    Returns the images in the order given, then the angle applied."""
    found = detect(image)
    angle = found['angle'] if found['confidence'] >= MIN_CONFIDENCE else 0
    if not angle:
        return (image, *companions, 0)
    turned = []
    for picture in (image, *companions):
        if picture is None:
            turned.append(None)
            continue
        turned.append(picture.rotate(angle, expand=True))
        picture.close()
    return (*turned, angle)
