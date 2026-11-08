"""Read Surya layout text blocks line by line with VietOCR."""
import functools
import os
import threading

_lock = threading.Lock()
_models = {}


def _load():
    with _lock:
        if not _models:
            import torch
            from surya.detection import DetectionPredictor
            from vietocr.tool.config import Cfg
            from vietocr.tool.predictor import Predictor
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            detector = DetectionPredictor.local(
                checkpoint=os.path.abspath(os.getenv('SURYA_TEXT_DETECTION_PATH', 'scratch/a3-models/surya-text-detection')),
                device=device)
            detector.disable_tqdm = True
            config = Cfg.load_config_from_name('vgg_transformer')
            config['weights'] = os.path.abspath(os.getenv('VIETOCR_WEIGHTS', 'scratch/a3-models/vietocr/vgg_transformer.pth'))
            config['device'] = 'cuda:0' if device == 'cuda' else 'cpu'
            config['predictor']['beamsearch'] = False
            # VietOCR loads its checkpoint with plain torch.load; refuse pickled code.
            original = torch.load
            torch.load = functools.partial(original, weights_only=True)
            try:
                reader = Predictor(config)
            finally:
                torch.load = original
            _models.update(detector=detector, reader=reader)
    return _models['detector'], _models['reader']


def unload():
    with _lock:
        if not _models:
            return
        _models.clear()
    import torch
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def lines_in_blocks(lines, blocks, width):
    """Give each detected line to one block and order that block's lines for reading."""
    margin, row = max(4, width//300), max(8, width//124)
    used, grouped = set(), []
    for x0, y0, x1, y1 in blocks:
        inside = [(index, line) for index, line in enumerate(lines) if index not in used
                  and x0-margin <= (line[0]+line[2])/2 <= x1+margin
                  and y0-margin <= (line[1]+line[3])/2 <= y1+margin]
        used.update(index for index, _ in inside)
        inside.sort(key=lambda item: (round(item[1][1]/row), item[1][0]))
        # A block with no detected line is still read whole rather than dropped.
        grouped.append([line for _, line in inside] or [[x0, y0, x1, y1]])
    return grouped


LINE_BATCH = 64


def read_lines(image, split=None, models=None):
    """Every detected text line with where it is, what it says and VietOCR's probability for it.
    split may cut detected boxes first, e.g. where a line runs over a table's column boundary."""
    detector, reader = models or _load()
    boxes = [list(line.bbox) for line in detector([image])[0].bboxes]
    if split:
        boxes = split(boxes)
    width, height = image.size
    crops = [image.crop((max(0, int(x0)-4), max(0, int(y0)-4), min(width, int(x1)+4), min(height, int(y1)+4)))
             for x0, y0, x1, y1 in boxes]
    read, probability = [], []
    for offset in range(0, len(crops), LINE_BATCH):
        texts, probs = reader.predict_batch(crops[offset:offset+LINE_BATCH], return_prob=True)
        read.extend(texts)
        probability.extend(float(p) for p in probs)
    return [dict(bbox=box, text=text.strip(), probability=p) for box, text, p in zip(boxes, read, probability) if text.strip()]


CELL_PIECE = 8  # pixels: a line is cut at a cell edge only into pieces this wide


def split_at_cell_edges(lines, blocks):
    """Cut a detected line where it runs from one block into the next at the same height.
    Table headers sit close across a thin rule: "Mã dịch vụ" and "Tên dịch vụ" came back as one line, so the
    first cell read both and the second, left with no line, was read whole as "Tên địch nay". A block spanning
    several columns, such as "Hao phí", has no edge inside it at that height and its line stays whole."""
    pieces = []
    for x0, y0, x1, y1 in lines:
        middle = (y0+y1)/2
        edges = sorted({edge for bx0, by0, bx1, by1 in blocks if by0 <= middle <= by1 for edge in (bx0, bx1)
                        if x0+CELL_PIECE < edge < x1-CELL_PIECE})
        cuts = [x0, *edges, x1]
        pieces.extend([a, y0, b, y1] for a, b in zip(cuts, cuts[1:]))
    return pieces


def read_blocks(image, blocks, models=None, confidence=False, split_lines=False):
    """Return one text per block; pixels outside the supplied blocks are not read.
    A page's lines go to the model in batches: one call per line left the GPU waiting between calls.
    With confidence, each block also carries the lowest probability VietOCR gave one of its lines.
    split_lines cuts lines at block edges, for table cells that touch."""
    if not blocks:
        return []
    detector, reader = models or _load()
    lines = [line.bbox for line in detector([image])[0].bboxes]
    if split_lines:
        lines = split_at_cell_edges(lines, blocks)
    width, height = image.size
    grouped = lines_in_blocks(lines, blocks, width)
    crops = [image.crop((max(0, int(x0)-4), max(0, int(y0)-4), min(width, int(x1)+4), min(height, int(y1)+4)))
             for block_lines in grouped for x0, y0, x1, y1 in block_lines]
    read, probability = [], []
    for offset in range(0, len(crops), LINE_BATCH):
        if confidence:
            texts, probs = reader.predict_batch(crops[offset:offset+LINE_BATCH], return_prob=True)
            read.extend(texts)
            probability.extend(float(p) for p in probs)
        else:
            read.extend(reader.predict_batch(crops[offset:offset+LINE_BATCH]))
    texts, cursor = [], 0
    for block_lines in grouped:
        parts = read[cursor:cursor+len(block_lines)]
        text = '\n'.join(part for part in parts if part.strip())
        texts.append((text, min(probability[cursor:cursor+len(block_lines)], default=0.)) if confidence else text)
        cursor += len(block_lines)
    return texts
