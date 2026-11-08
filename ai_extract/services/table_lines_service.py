"""Rebuild table body rows from the positions of text lines, column by column.

A rate table often rules only its frame: the body is one physical band holding many text lines. Rows taken
from a learned row detector then drift from the text. On the BXD appendix, page 15, every value after
"Thiết bị kiểm tra đèn chiếu sáng / phía trước" (a name over two lines) moved one row down: "Thiết bị đo khí
thải" got 0,0042 instead of 0,0085, and the last row was lost.

Here a band's rows come from its name column, the column with the most lines. A value level with a name line
belongs to it; a value midway between two name lines marks one name wrapped over both. A name line with no
value joins the line above only when it sits closer to it than rows sit to each other (a wrapped heading such
as "Vật liệu, nhiên liệu, dụng cụ / lao động"); otherwise it stays a row of its own (a heading such as
"Nhân công"). A column whose lines form one unbroken block, such as a service name merged down the body, or
whose single line sits mid-band, stays one merged cell. A value that fits none of this, or two values landing
in one row, marks the table for review instead of being placed silently.
Only geometry is used; the text of a line never decides where it goes. The first band (the header) and bands
holding one logical row keep the grid they were given, with its spans.
"""
import statistics

ALIGN = .35          # of the median line height: a value this close to a name line is level with it
FULL_RULE = .85      # of the table width: a rule this long separates bands
MIN_BODY_LINES = 3   # name lines that make a band worth realigning
WRAP_GAP = .88       # of the median gap between name lines: closer than this is one wrapped name
FULL_LINE = .15      # of the column width: a line ending this close to the column's right edge is full
MIN_PIECE = 8        # pixels: a detected line crossing a column cut is split only into pieces this wide
WARNING = 'row_alignment_unverified'


def _center(box):
    return (box[1]+box[3])/2


def _column(box, x_cuts):
    middle = (box[0]+box[2])/2
    for index in range(len(x_cuts)-1):
        if x_cuts[index] <= middle < x_cuts[index+1]:
            return index
    return 0 if middle < x_cuts[0] else len(x_cuts)-2


def split_at_columns(boxes, x_cuts):
    """A detected line running over a column boundary is two cells' text: cut it there."""
    pieces = []
    for x0, y0, x1, y1 in boxes:
        edges = [x0, *(cut for cut in x_cuts[1:-1] if x0+MIN_PIECE < cut < x1-MIN_PIECE), x1]
        pieces.extend([a, y0, b, y1] for a, b in zip(edges, edges[1:]))
    return pieces


def bands(horizontal, x_cuts, top, bottom):
    width = x_cuts[-1]-x_cuts[0]
    cuts = sorted({round(line[1]) for line in horizontal if line[2]-line[0] >= width*FULL_RULE and top < line[1] < bottom})
    edges = [top, *cuts, bottom]
    return [(a, b) for a, b in zip(edges, edges[1:]) if b-a > 2]


def _merged_column(lines, pitch, band):
    """One unbroken block of lines, or one line near the band's middle: a cell merged down the band."""
    centers = sorted(_center(line['bbox']) for line in lines)
    if len(centers) == 1:
        return abs(centers[0]-(band[0]+band[1])/2) <= (band[1]-band[0])*.15
    return all(b-a <= pitch*1.5 for a, b in zip(centers, centers[1:]))


def _pitch(lines):
    return statistics.median([line['bbox'][3]-line['bbox'][1] for line in lines] or [1])


def _visual_lines(lines, pitch):
    """Boxes of one column at one height are one visual line: justified text such as
    "Phôi   giấy   chứng   nhận," came back as three boxes, and counted as three name lines."""
    merged = []
    for line in sorted(lines, key=lambda l: _center(l['bbox'])):
        last = merged[-1] if merged else None
        if last and abs(_center(line['bbox'])-_center(last['parts'][0]['bbox'])) < pitch*.5:
            last['parts'].append(line)
        else:
            merged.append(dict(parts=[line]))
    result = []
    for group in merged:
        parts = sorted(group['parts'], key=lambda l: l['bbox'][0])
        boxes = [p['bbox'] for p in parts]
        result.append(dict(parts[0], text=' '.join(p.get('text', '') for p in parts).strip(),
                           bbox=[min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]))
    return result


def body_bands(lines, x_cuts, horizontal, top, bottom):
    """Bands below the header whose lines hold several logical rows."""
    columns, pitch, chosen = len(x_cuts)-1, _pitch(lines), []
    for band in text_bands(lines, x_cuts, horizontal, top, bottom)[1:]:
        inside = [l for l in lines if band[0] <= _center(l['bbox']) < band[1]]
        per_column = [_visual_lines([l for l in inside if _column(l['bbox'], x_cuts) == c], pitch) for c in range(columns)]
        name = max(range(columns), key=lambda c: len(per_column[c]))
        values = [c for c in range(columns) if c != name and per_column[c] and not _merged_column(per_column[c], pitch, band)]
        if len(per_column[name]) >= MIN_BODY_LINES and any(len(per_column[c]) >= 2 for c in values):
            chosen.append(band)
    return chosen


def align_band(lines, x_cuts, band, pitch):
    """Rows of one band: (rows of texts, cells numbered from 1 within the band, issues: values that fit no row or share one)."""
    a, b = band
    columns = len(x_cuts)-1
    inside = [l for l in lines if a <= _center(l['bbox']) < b]
    per_column = [_visual_lines([l for l in inside if _column(l['bbox'], x_cuts) == c], pitch) for c in range(columns)]
    name = max(range(columns), key=lambda c: len(per_column[c]))
    names = per_column[name]
    centers = [_center(l['bbox']) for l in names]
    tolerance = pitch*ALIGN
    merged = {c for c in range(columns) if c != name and per_column[c] and _merged_column(per_column[c], pitch, band)}
    issues, joins, placed = [], set(), {}
    for c in range(columns):
        if c == name or c in merged:
            continue
        for line in per_column[c]:
            y = _center(line['bbox'])
            nearest = min(range(len(centers)), key=lambda i: abs(centers[i]-y))
            anchor = nearest
            if abs(centers[nearest]-y) > tolerance:
                upper = nearest if centers[nearest] < y else nearest-1
                if 0 <= upper < len(centers)-1 and abs((centers[upper]+centers[upper+1])/2-y) <= tolerance:
                    anchor = upper
                    joins.add(upper)
                else:
                    issues.append(dict(kind='value_beside_no_name_line', text=line['text'], y=round(y),
                                       nearest=names[nearest]['text']))
            placed.setdefault(anchor, {}).setdefault(c, []).append(line)
    gaps = [q-p for p, q in zip(centers, centers[1:])]
    usual = statistics.median(gaps) if gaps else 0
    # A name line with no value continues the line above when it sits closer than rows do, or when the line
    # above has no value either and runs to the column's edge: it wrapped for want of room. Page 21 spaces
    # "Vật liệu, nhiên liệu, dụng cụ / lao động" like separate rows. "Nhân công" follows a line with values
    # and stays a heading of its own.
    edge = x_cuts[name+1]-FULL_LINE*(x_cuts[name+1]-x_cuts[name])
    for index in range(1, len(names)):
        if index in placed or index-1 in joins:
            continue
        if gaps[index-1] < usual*WRAP_GAP or (index-1 not in placed and names[index-1]['bbox'][2] >= edge):
            joins.add(index-1)
    groups, current = [], [0]
    for index in range(1, len(names)):
        if index-1 in joins:
            current.append(index)
        else:
            groups.append(current)
            current = [index]
    groups.append(current)
    rows, cells = [], []
    for number, group in enumerate(groups):
        values = {}
        for index in group:
            for c, found in placed.get(index, {}).items():
                values.setdefault(c, []).extend(found)
        texts = ['']*columns
        texts[name] = ' '.join(names[i]['text'] for i in group)
        for c, found in values.items():
            if len(found) > 1:
                issues.append(dict(kind='several_values_in_one_row', text=' / '.join(l['text'] for l in found),
                                   nearest=texts[name]))
            texts[c] = ' / '.join(l['text'] for l in sorted(found, key=lambda l: _center(l['bbox'])))
        top_y = a if number == 0 else (centers[groups[number-1][-1]]+centers[group[0]])/2
        bottom_y = b if number == len(groups)-1 else (centers[group[-1]]+centers[groups[number+1][0]])/2
        rows.append(texts)
        for column in range(columns):
            if column not in merged:
                cells.append(dict(row=len(rows), column=column+1, rowspan=1, colspan=1, text=texts[column],
                                  bbox=[x_cuts[column], top_y, x_cuts[column+1], bottom_y]))
    for column in merged:
        text = ' '.join(l['text'] for l in per_column[column])
        rows[0][column] = text
        cells.append(dict(row=1, column=column+1, rowspan=len(rows), colspan=1, text=text,
                          bbox=[x_cuts[column], a, x_cuts[column+1], b]))
    for cell in cells:
        cell.update(header=False, ocr_status='completed', ocr_engine='vietocr', row_origin='text_line_positions')
    return rows, cells, issues


def band_row(lines, x_cuts, band):
    """A band holding one logical row, such as a header, as one row: each column's lines in reading order.
    Used when the given grid cannot be kept because its rows cross the band's rules."""
    columns = len(x_cuts)-1
    inside_band = [l for l in lines if band[0] <= _center(l['bbox']) < band[1]]
    texts = [' '.join(l['text'] for l in sorted((l for l in inside_band if _column(l['bbox'], x_cuts) == c),
                                                key=lambda l: (round(_center(l['bbox'])), l['bbox'][0]))) for c in range(columns)]
    cells = [dict(row=1, column=c+1, rowspan=1, colspan=1, text=texts[c], bbox=[x_cuts[c], band[0], x_cuts[c+1], band[1]],
                  header=False, ocr_status='completed', ocr_engine='vietocr', row_origin='text_line_positions')
             for c in range(columns)]
    return [texts], cells, []


def header_grid(lines, x_cuts, band, segments, vertical, slack=4):
    """A header band as cells drawn by its own rules, for a table whose given grid could not be kept.
    A short horizontal rule splits only the columns it runs under ("Hao phí" over "Hao phí kiểm định" and
    "Hao phí cấp GCN"); two neighbouring cells merge where no vertical rule runs the height between them, so
    "Hao phí" spans two columns and "Mã dịch vụ" two rows. Falls back to one row when no rule splits the band."""
    a, b = band
    columns = len(x_cuts)-1
    width = lambda c: x_cuts[c+1]-x_cuts[c]
    splits = [sorted({round(s[1]) for s in segments if a+slack < s[1] < b-slack
                      and s[0] <= x_cuts[c]+.1*width(c) and s[2] >= x_cuts[c+1]-.1*width(c)}) for c in range(columns)]
    edges = sorted({a, b, *(y for column in splits for y in column)})
    merged_edges = []
    for y in edges:
        if merged_edges and y-merged_edges[-1] <= slack:
            continue
        merged_edges.append(y)
    if merged_edges[-1] != b:
        merged_edges[-1] = b
    if len(merged_edges) <= 2:
        return band_row(lines, x_cuts, band)
    snap = lambda y: min(range(len(merged_edges)), key=lambda i: abs(merged_edges[i]-y))
    # Each column's own pieces as (first row, last row) over the band's row edges.
    pieces = []
    for c in range(columns):
        own = [0, *sorted({snap(y) for y in splits[c]}), len(merged_edges)-1]
        pieces.append([(top, bottom-1) for top, bottom in zip(own, own[1:]) if bottom > top])

    def ruled(cut, top, bottom):
        y0, y1 = merged_edges[top]+slack, merged_edges[bottom+1]-slack
        return any(abs(rule[0]-x_cuts[cut]) <= .02*(x_cuts[-1]-x_cuts[0]) and rule[1] <= y0 and rule[3] >= y1
                   for rule in vertical)
    cells, taken = [], set()
    for c in range(columns):
        for top, bottom in pieces[c]:
            if (top, c) in taken:
                continue
            span = 1
            while c+span < columns and (top, bottom) in pieces[c+span] and not ruled(c+span, top, bottom):
                span += 1
            box = [x_cuts[c], merged_edges[top], x_cuts[c+span], merged_edges[bottom+1]]
            text = ' '.join(l['text'] for l in sorted(
                (l for l in lines if box[0] <= (l['bbox'][0]+l['bbox'][2])/2 < box[2] and box[1] <= _center(l['bbox']) < box[3]),
                key=lambda l: (round(_center(l['bbox'])), l['bbox'][0])))
            cells.append(dict(row=top+1, column=c+1, rowspan=bottom-top+1, colspan=span, text=text, bbox=box,
                              header=True, ocr_status='completed', ocr_engine='vietocr', row_origin='text_line_positions'))
            taken.update((r, c+k) for r in range(top, bottom+1) for k in range(span))
    rows = [['']*columns for _ in range(len(merged_edges)-1)]
    for cell in cells:
        rows[cell['row']-1][cell['column']-1] = cell['text']
    return rows, cells, []


def text_bands(lines, x_cuts, horizontal, top, bottom):
    return [band for band in bands(horizontal, x_cuts, top, bottom)
            if any(band[0] <= _center(l['bbox']) < band[1] for l in lines)]


def inside(cell, band, slack):
    return band[0]-slack <= cell['bbox'][1] and cell['bbox'][3] <= band[1]+slack


def straddles(cell, chosen, slack):
    """A grid cell reaching across the edge of a band about to be rebuilt: the two cannot be combined."""
    top, bottom = cell['bbox'][1], cell['bbox'][3]
    return any(min(bottom, b)-max(top, a) > slack and not inside(cell, (a, b), slack) for a, b in chosen)


def assemble(grid_cells, chosen, aligned, columns):
    """Grid cells outside the rebuilt bands plus the rebuilt rows, renumbered top to bottom.
    grid_cells: cells of the given grid lying outside every chosen band. aligned: align_band output per band."""
    pieces = []
    for original in sorted({c['row'] for c in grid_cells}):
        tops = [c['bbox'][1] for c in grid_cells if c['row'] == original]
        pieces.append((min(tops), 'grid', original))
    for band, result in zip(chosen, aligned):
        pieces.append((band[0], 'band', result))
    pieces.sort(key=lambda piece: piece[0])
    rows, cells, renumber = [], [], {}
    for _, kind, value in pieces:
        if kind == 'grid':
            rows.append(['']*columns)
            renumber[value] = len(rows)
        else:
            offset = len(rows)
            rows.extend(list(row) for row in value[0])
            cells.extend(dict(cell, row=cell['row']+offset) for cell in value[1])
    for cell in grid_cells:
        cells.append(dict(cell, row=renumber[cell['row']]))
    for cell in cells:
        rows[cell['row']-1][cell['column']-1] = cell['text']
    cells.sort(key=lambda c: (c['row'], c['column']))
    return rows, cells
