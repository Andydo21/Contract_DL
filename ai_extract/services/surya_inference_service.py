"""Surya OCR inference and source block normalization without web ORM imports."""
import base64
import io
import json
import math
import os
import time
import subprocess
import atexit
from pathlib import Path
from threading import RLock
from urllib.request import urlopen
from urllib.parse import urlparse
from copy import copy
from concurrent.futures import ThreadPoolExecutor

_managed_backend = None
VISUAL_OCR_POLICY = 'surya-image-text-only-v21-cross-prompt'
BODY_OCR_POLICY = 'surya-high-resolution-v3-source-html'


def native_reading_order(blocks, scope='page', source='surya_layout_model'):
    """Use Surya's trained output order, never OCR completion time or bbox sorting.

    Surya 2 exposes the layout sequence as reading_order (box.position).
    Validate the sequence structurally; this is not a visual accuracy score.
    Missing/duplicate ranks retain evidence but cannot authorize NEXT edges.
    """
    blocks = list(blocks)
    ranks = [getattr(block, 'reading_order', None) for block in blocks]
    valid = all(type(rank) is int and rank >= 0 for rank in ranks)
    valid = valid and len(set(ranks)) == len(ranks)
    ordered = sorted(zip(blocks, ranks), key=lambda item: item[1]) if valid else zip(blocks, ranks)
    return [(block, dict(reading_order=rank if type(rank) is int and rank >= 0 else None,
                         reading_order_source=source, reading_order_scope=scope,
                         reading_order_status='model_predicted' if valid else 'unresolved',
                         reading_order_unresolved=not valid)) for block, rank in ordered]


class ManagedSuryaBackend:
    """Own the existing local binary, restart crashes without downloading weights."""

    def __init__(self, backend):
        self.backend, self.process = backend, None
        self.lock = RLock()
        self.url = os.environ['SURYA_INFERENCE_URL'].rstrip('/')
        parsed = urlparse(self.url)
        if parsed.hostname not in {'127.0.0.1', 'localhost'} or parsed.scheme != 'http':
            raise ValueError('Managed Surya requires a local HTTP endpoint')
        self.port = parsed.port
        atexit.register(self.suspend)

    def ready(self):
        try:
            with urlopen(self.url+'/models', timeout=2) as response:
                return any(row['id'] == 'datalab-to/surya-ocr-2'
                           for row in json.load(response).get('data', []))
        except (OSError, ValueError, KeyError):
            return False

    def start(self):
        with self.lock:
            if not self.ready():
                self.suspend()
                binary = Path(os.environ['LLAMA_CPP_BINARY'])
                model = Path(os.environ['SURYA_GGUF_LOCAL_MODEL_PATH'])
                projection = Path(os.environ['SURYA_GGUF_LOCAL_MMPROJ_PATH'])
                template = model.parent/'chat_template.jinja'
                if not all(path.is_file() for path in (binary, model, projection, template)):
                    raise RuntimeError('Existing local Surya files are unavailable')
                # Never start over an unrelated service bound to this port.
                import socket
                with socket.socket() as check:
                    if check.connect_ex(('127.0.0.1', self.port)) == 0:
                        raise RuntimeError('Surya port is occupied by an unhealthy or different service')
                command = [str(binary), '-m', str(model), '--mmproj', str(projection),
                    '--chat-template-file', str(template), '--image-min-tokens', '1024',
                    '--alias', 'datalab-to/surya-ocr-2', '--host', '127.0.0.1', '--port', str(self.port),
                    '--parallel', os.getenv('SURYA_INFERENCE_PARALLEL', '2'),
                    '--ctx-size', os.getenv('SURYA_INFERENCE_CTX_SIZE', '32768'),
                    '--n-gpu-layers', '99', '--jinja']
                log = model.parent.parent.parent/'surya-managed.log'
                with log.open('ab') as output:
                    self.process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                print(json.dumps(dict(event='surya_backend', status='starting', pid=self.process.pid)), flush=True)
                deadline = time.monotonic()+60
                while not self.ready():
                    if self.process.poll() is not None or time.monotonic() >= deadline:
                        self.suspend()
                        raise RuntimeError('Surya backend could not recover within startup budget')
                    time.sleep(.25)
                self.backend.stop()  # Invalidate the library's stale HTTP handle.
                print(json.dumps(dict(event='surya_backend', status='ready', pid=self.process.pid)), flush=True)
            return self.backend.start()

    def capacity(self):
        return self.backend.capacity()

    def suspend(self):
        with self.lock:
            if self.process is not None:
                if self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=5)
                self.process = None
                self.backend.stop()
                print(json.dumps(dict(event='surya_backend', status='released')), flush=True)


def release_surya_backend():
    """Release only the process owned by this runtime, for CUDA recovery."""
    if _managed_backend is not None:
        _managed_backend.suspend()


def repeating_output(text):
    """Detect repeated content, not indentation or a drawing's separator line."""
    tail = ' '.join(text[-4000:].split())
    for cut in (0, 50):
        value = tail[:-cut] if cut else tail
        for size in range(24, min(500, len(value)//4)+1):
            unit = value[-size:]
            if any(char.isalnum() for char in unit) and value.endswith(unit*4):
                return True
    return False


def frame_text_crop(image, rescue=False):
    """Keep every source pixel; give tiny/narrow text stable image-grid margins."""
    from PIL import Image, ImageOps
    if not rescue and image.height>=48 and image.width<=12*image.height:
        return image
    crop=image.convert('RGB')
    if rescue:crop=ImageOps.autocontrast(crop)
    scale=min(4,max(1,64/crop.height),2048/crop.width)
    if scale>1:
        crop=crop.resize((round(crop.width*scale),round(crop.height*scale)),Image.Resampling.LANCZOS)
    frame=Image.new('RGB',(max(256,crop.width+32),max(128,crop.height+32)),'white')
    frame.paste(crop,((frame.width-crop.width)//2,(frame.height-crop.height)//2))
    return frame


class SuryaStreamManager:
    """Use Surya's prompts/parsers, cancel repetition before decoding a whole page again."""

    def __init__(self, manager):
        self.manager = manager
        self.client = None
        self.begin_page()

    def begin_page(self):
        self.started = time.perf_counter()
        self.calls = []

    def generate(self, batch, *, retry=False, retry_reason=None, rescue=False):
        if not batch:
            return []
        from openai import OpenAI
        from surya.inference.prompts import PROMPT_MAPPING
        from surya.inference.schema import BatchOutputItem
        from surya.inference.util import scale_to_fit
        from surya.settings import settings
        handle = self.manager.backend.start()
        if self.client is None:
            # Disable hidden HTTP retries as well as the library's three OCR retries.
            self.client = OpenAI(api_key='EMPTY', base_url=handle.base_url, max_retries=0)
        def read(item):
            started = time.perf_counter()
            page_budget = float(os.getenv('SURYA_PAGE_GENERATION_TIMEOUT', '0'))
            request_budget = float(os.getenv('SURYA_REQUEST_GENERATION_TIMEOUT', '0'))
            remaining = page_budget-(started-self.started) if page_budget>0 else float('inf')
            limit = min(remaining,request_budget if request_budget>0 else float('inf'))
            visual_block=item.prompt_type=='block' and (item.metadata.get('visual_ocr') or getattr(self,'visual_phase',False))
            crop=frame_text_crop(item.image,rescue=True) if visual_block and rescue else item.image
            buffer = io.BytesIO()
            submitted_image=scale_to_fit(crop)
            submitted_image.save(buffer, format='PNG')
            messages = [dict(role='user', content=[dict(type='image_url', image_url=dict(
                url='data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode('ascii'))),
                dict(type='text', text=item.prompt or PROMPT_MAPPING[item.prompt_type])])]
            token_budget = item.max_tokens or 2048
            if item.prompt_type == 'block':
                # Layout count estimates omit markup/code punctuation. Provide headroom
                # up front; EOS still ends short crops immediately without a retry.
                minimum=max(1024,int(os.getenv('SURYA_MIN_BLOCK_TOKENS','1024')))
                if retry:minimum*=2
                token_budget = min(8192, max(minimum, token_budget*2))
                if rescue:token_budget=min(token_budget,1024)
            options = dict(model=handle.model_name, messages=messages, stream=True,
                stream_options={'include_usage': True}, temperature=0,
                top_p=.1,
                max_tokens=token_budget, timeout=max(1, min(limit, 30)),
                logprobs=bool(item.request_logprobs or settings.SURYA_INFERENCE_LOGPROBS))
            if item.guided_json is not None:
                options['response_format'] = dict(type='json_schema', json_schema=dict(
                    name='surya_layout', schema=item.guided_json, strict=True))
            if item.guided_regex is not None:
                options['extra_body'] = {'guided_regex': item.guided_regex}
            raw, status, tokens, logprobs, last_check = '', 'unfinished', 0, [], 0
            try:
                if limit <= 0:
                    raise TimeoutError('Surya page generation budget exceeded')
                with self.client.chat.completions.create(**options) as stream:
                    for chunk in stream:
                        if time.perf_counter()-started >= limit:
                            status = 'deadline_exceeded'
                            break
                        if chunk.usage:
                            tokens = chunk.usage.completion_tokens
                        if not chunk.choices:
                            continue
                        choice = chunk.choices[0]
                        raw += choice.delta.content or ''
                        if choice.logprobs and choice.logprobs.content:
                            logprobs.extend(entry.model_dump() for entry in choice.logprobs.content)
                        whitespace_run = len(raw)-len(raw.rstrip(' \t\u00a0'))
                        if whitespace_run >= max(256, item.image.width//2):
                            status = 'whitespace_loop_cancelled'
                            break
                        if len(raw) >= (384 if rescue else 1000) and len(raw)-last_check >= (128 if rescue else 200):
                            last_check = len(raw)
                            if repeating_output(raw):
                                status = 'repetition_cancelled'
                                break
                        if choice.finish_reason:
                            status = 'completed' if choice.finish_reason == 'stop' else 'token_budget_exceeded'
                # Closing the SSE stream cancels the llama.cpp task, including loops.
            except Exception as error:
                status = type(error).__name__
            probabilities = [math.exp(entry['logprob']) for entry in logprobs if entry.get('logprob') is not None]
            mean = sum(probabilities)/len(probabilities) if probabilities else None
            event = dict(prompt=item.prompt_type, status=status, elapsed_s=round(time.perf_counter()-started, 3),
                         output_tokens=tokens or None, output_chars=len(raw), retries=int(retry),
                         block_index=item.metadata.get('block_idx'), max_new_tokens=token_budget,
                         retry_reason=retry_reason, rescue=rescue, region_index=item.metadata.get('page_idx'),
                         source_image_size=list(item.image.size), input_image_size=list(submitted_image.size))
            if item.metadata.get('visual_ocr') or getattr(self,'visual_phase',False):
                event['visual_ocr'] = True
            self.calls.append(event)
            print(json.dumps(dict(event='surya_runtime', **event)), flush=True)
            if (not retry and item.prompt_type == 'block' and
                    status in {'whitespace_loop_cancelled', 'token_budget_exceeded',
                               'APITimeoutError', 'APIConnectionError', 'ReadError', 'RemoteProtocolError'} and
                    (page_budget<=0 or time.perf_counter()-self.started < page_budget)):
                # Retry only this failed crop once; optional deadlines are opt-in.
                replacement = copy(item)
                if status == 'whitespace_loop_cancelled':
                    from PIL import Image
                    # Wider framing prevents the decoder's endless <pre> indentation.
                    # Every original pixel and the source layout bbox remain unchanged.
                    framed = Image.new('RGB', (int(item.image.width*1.32), item.image.height), 'white')
                    framed.paste(item.image.convert('RGB'), (0, 0))
                    replacement.image = framed
                # Transport failure does not justify changing pixels, sampling or
                # token budget. Retry the original crop; completed siblings stay.
                if status not in {'APITimeoutError', 'APIConnectionError', 'ReadError', 'RemoteProtocolError'}:
                    replacement.max_tokens = min(4096, (item.max_tokens or 2048)*2)
                return self.generate([replacement], retry=True, retry_reason=status)[0]
            if (visual_block and retry and not rescue and
                    status == 'whitespace_loop_cancelled' and
                    (page_budget<=0 or time.perf_counter()-self.started<page_budget)):
                # One final, deterministic rescue; never repeat successful siblings
                # or recurse through pictures. Failed output remains unavailable.
                replacement=copy(item)
                replacement.temperature,replacement.top_p=0,.1
                return self.generate([replacement],retry=True,retry_reason=status,rescue=True)[0]
            return BatchOutputItem(raw=raw if status == 'completed' else '', token_count=tokens,
                error=status != 'completed', mean_token_prob=mean, logprobs=logprobs,
                metadata=item.metadata)
        workers = min(len(batch), max(1, int(os.getenv('SURYA_CROP_CONCURRENCY', '2'))),
                      self.manager.backend.capacity())
        if workers <= 1:
            return [read(item) for item in batch]
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='surya-crop') as pool:
            # map retains source order even when a later crop finishes first.
            return list(pool.map(read, batch))


def create_surya_predictor():
    """One Surya backend, with bounded streaming over layout and OCR crops."""
    from surya.inference import SuryaInferenceManager
    from surya.recognition import RecognitionPredictor
    global _managed_backend
    manager = SuryaInferenceManager()
    if os.getenv('SURYA_MANAGED_BACKEND') == '1':
        if _managed_backend is None:
            _managed_backend = ManagedSuryaBackend(manager.backend)
        manager.backend = _managed_backend
    return RecognitionPredictor(SuryaStreamManager(manager))

def _html_text(html):
    from html.parser import HTMLParser

    class TextParser(HTMLParser):

        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts = []

        def handle_starttag(self, tag, attrs):
            if tag in {'br', 'p', 'div', 'li', 'tr', 'h1', 'h2', 'h3', 'h4'}:
                self.parts.append('\n')

        def handle_endtag(self, tag):
            if tag in {'td', 'th'}:
                self.parts.append('\t')
            elif tag in {'p', 'div', 'li', 'tr', 'h1', 'h2', 'h3', 'h4'}:
                self.parts.append('\n')

        def handle_data(self, data):
            self.parts.append(data)
    parser = TextParser()
    parser.feed(html)
    parser.close()
    return '\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip())


def source_html_metadata(html):
    """Preserve Surya's explicit HTML structure; never infer levels or columns."""
    from html.parser import HTMLParser

    class StructureParser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.rows, self.cells, self.headings = [], [], []
            self.row, self.cell, self.heading, self.table_depth = None, None, None, 0

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'table': self.table_depth += 1
            if tag in {'h1','h2','h3','h4','h5','h6'}:
                self.heading = dict(level=int(tag[1]),parts=[])
            if self.table_depth == 1 and tag == 'tr': self.row = []
            if self.table_depth == 1 and self.row is not None and tag in {'td','th'}:
                try:
                    rowspan, colspan = int(attrs.get('rowspan',1)), int(attrs.get('colspan',1))
                    if not 1 <= rowspan <= 200 or not 1 <= colspan <= 100: return
                except (TypeError,ValueError): return
                self.cell = dict(parts=[],rowspan=rowspan,colspan=colspan,header=tag=='th')
            if tag == 'br': self.handle_data('\n')

        def handle_data(self, data):
            if self.cell is not None: self.cell['parts'].append(data)
            if self.heading is not None: self.heading['parts'].append(data)

        def handle_endtag(self, tag):
            if tag in {'h1','h2','h3','h4','h5','h6'} and self.heading is not None:
                self.headings.append(self.heading); self.heading = None
            if tag in {'td','th'} and self.cell is not None:
                self.row.append(self.cell); self.cell = None
            if tag == 'tr' and self.row is not None:
                self.rows.append(self.row); self.row = None
            if tag == 'table': self.table_depth = max(0,self.table_depth-1)

    parser = StructureParser()
    parser.feed(html or ''); parser.close()
    metadata = {}
    if len(parser.headings) == 1 and ''.join(parser.headings[0]['parts']).strip() == _html_text(html).strip():
        metadata.update(heading_level=parser.headings[0]['level'],heading_source='surya_html',
                        hierarchy_level_status='model_supplied')
    if parser.rows:
        occupied, cells, rows = set(), [], []
        for row_number, row in enumerate(parser.rows,1):
            column = 1
            for cell in row:
                while (row_number,column) in occupied: column += 1
                value = ''.join(cell.pop('parts')).strip()
                cells.append(dict(row=row_number,column=column,text=value,**cell))
                for r in range(row_number,row_number+cell['rowspan']):
                    for c in range(column,column+cell['colspan']): occupied.add((r,c))
                column += cell['colspan']
            width = max((c for r,c in occupied if r==row_number),default=0)
            rows.append([next((c['text'] for c in cells if c['row']==row_number and c['column']==col),'')
                         for col in range(1,width+1)])
        metadata.update(table_rows=rows,table_cells=cells,table_header_origin='surya_html_unreviewed',
                        table_structure_status='model_supplied')
    return metadata


def _visual_layout(crops, manager):
    from surya.layout import LayoutPredictor
    from PIL import Image
    frames, offsets = [], []
    for crop in crops:
        if crop.width<256 or crop.height<128:
            width,height=max(512,crop.width+32),max(512,crop.height+32)
            frame=Image.new('RGB',(width,height),'white')
            x,y=(width-crop.width)//2,(height-crop.height)//2
            frame.paste(crop,(x,y));frames.append(frame);offsets.append((x,y))
        else:
            frames.append(crop);offsets.append((0,0))
    detect=LayoutPredictor(manager)
    results=detect(frames)
    failed=[i for i,result in enumerate(results) if getattr(result,'error',False)]
    if failed:
        # Retry only failed image layouts, once. This does not descend into
        # nested pictures; translate the rescue margins back to source pixels.
        rescued=[]
        for i in failed:
            frame=Image.new('RGB',(frames[i].width+64,frames[i].height+64),'white')
            frame.paste(frames[i],(32,32));rescued.append(frame)
        print(json.dumps(dict(event='surya_visual_layout_retry',regions=failed,attempt=1)),flush=True)
        retries=detect(rescued)
        if len(retries)!=len(failed):raise RuntimeError('Visual layout retry count mismatch')
        for i,result in zip(failed,retries):
            results[i]=result
            offsets[i]=(offsets[i][0]+32,offsets[i][1]+32)
    for result,crop,(x,y) in zip(results,crops,offsets):
        if not (x or y):continue
        boxes=[]
        for box in result.bboxes:
            a,b,c,d=box.bbox
            a,b,c,d=max(0,a-x),max(0,b-y),min(crop.width,c-x),min(crop.height,d-y)
            if a>=c or b>=d:continue
            box.polygon=[[a,b],[c,b],[c,d],[a,d]]
            boxes.append(box)
        result.bboxes=boxes;result.image_bbox=[0,0,crop.width,crop.height]
    return results


def surya_visual_page(image, predictor, layout, *, reset_budget=True, high_resolution_image=None):
    """Run one extra layout -> block OCR pass inside each page image region.

    Each detected child is independent. Parent images never aggregate child
    text; IDs and bboxes retain the exact source containment and chunk boundary.
    """
    from .document_structure_service import normalize_layout
    manager = predictor.manager
    if reset_budget and isinstance(manager, SuryaStreamManager): manager.begin_page()
    started = time.perf_counter()
    calls_before = len(manager.calls) if isinstance(manager, SuryaStreamManager) else 0
    sharp = high_resolution_image or image
    if abs(sharp.width/sharp.height-image.width/image.height) > .01:
        raise ValueError('Visual source images must have the same page aspect ratio')
    sx, sy = sharp.width/image.width, sharp.height/image.height
    min_text_height=float(os.getenv('SURYA_VISUAL_MIN_TEXT_HEIGHT','6'))*image.height/1755
    if not math.isfinite(min_text_height) or min_text_height<0:raise ValueError('Invalid visual text size threshold')
    roots, children, pending = [], [], []

    def crop_for(box):
        from PIL import ImageDraw
        x0,y0=int(box[0]*sx),int(box[1]*sy)
        crop=sharp.crop((x0,y0,math.ceil(box[2]*sx),math.ceil(box[3]*sy)))
        draw=ImageDraw.Draw(crop)
        for text_box in text_boxes:
            left,top=max(box[0],text_box[0]),max(box[1],text_box[1])
            right,bottom=min(box[2],text_box[2]),min(box[3],text_box[3])
            if left<right and top<bottom:
                draw.rectangle((int(left*sx)-x0,int(top*sy)-y0,
                                math.ceil(right*sx)-x0-1,math.ceil(bottom*sy)-y0-1),fill='white')
        return crop

    def valid_box(box, width, height):
        return (len(box) == 4 and all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in box)
                and 0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height)

    # A picture bbox can overlap page text. Preserve ownership of that text
    # instead of reading clipped fragments into the picture's child chunks.
    text_boxes=[r['bbox'] for r in layout
        if normalize_layout(r.get('label')) in {'title','paragraph','list_item','list_group',
            'figure_caption','table_caption','table','code','formula','page_header','page_footer'}
        and r.get('ocr_status','completed')=='completed'
        and valid_box(r.get('bbox',[]),image.width,image.height)]

    def belongs_to_page_text(box):
        area=(box[2]-box[0])*(box[3]-box[1])
        return area>0 and any(max(0,min(box[2],b[2])-max(box[0],b[0]))*
            max(0,min(box[3],b[3])-max(box[1],b[1]))/area>=.9 for b in text_boxes)

    for index, region in enumerate(layout):
        if normalize_layout(region.get('label')) != 'figure': continue
        box = region.get('bbox', [])
        if not valid_box(box, image.width, image.height):
            raise ValueError('Visual OCR requires a valid page-pixel bbox')
        root = dict(index=index, bbox=box, label=region['label'], status='completed', text='',
                    ocr_lines=[], error_type='', confidence=0, children=[], candidate_failures=0,
                    candidate_rejections=0, unreadable_lines=0, excluded_page_text=0, ignored_tiny_text=0)
        roots.append(root)
        pending.append((region.get('region_id', f'surya:{index}'), box, 1, root))
    if isinstance(manager, SuryaStreamManager): manager.visual_phase = True
    try:
        # Exactly one batch of page-level image regions. Inner images are never queued.
        for wave in [pending] if pending else []:
            crops = [crop_for(box) for _,box,_,_ in wave]
            print(json.dumps(dict(event='surya_visual_layout', depth=wave[0][2], regions=len(wave))), flush=True)
            try:
                layouts = _visual_layout(crops, manager)
                if len(layouts) != len(wave): raise RuntimeError('Visual layout result count mismatch')
            except Exception as error:
                for _,_,_,root in wave:
                    root['candidate_failures'] += 1; root['error_type'] = type(error).__name__
                continue
            # Ignore unreadably small screenshot labels before any OCR call.
            # This leaves page text and readable labels inside pictures intact.
            for i,result in enumerate(layouts):
                if not hasattr(result,'bboxes'):continue
                kept=[]
                for box in result.bboxes:
                    bbox=box.bbox
                    if normalize_layout(getattr(box,'label','Text')) in {'title','paragraph','list_item','list_group','page_header','page_footer','figure_caption','table_caption'} and (bbox[3]-bbox[1])/sy<min_text_height:
                        wave[i][3]['ignored_tiny_text']+=1
                    else:kept.append(box)
                result.bboxes=kept
            # OCR only regions labelled as text/table/etc by this layout pass.
            # The same RecognitionPredictor skips inner images; they are saved as-is.
            usable = [(i, result) for i,result in enumerate(layouts) if not result.error]
            try:
                recognized = predictor([crops[i] for i,_ in usable],
                                      layout_results=[result for _,result in usable], full_page=False) if usable else []
                if len(recognized) != len(usable): raise RuntimeError('Visual OCR result count mismatch')
                by_index = {i:r for (i,_),r in zip(usable, recognized)}
            except Exception as error:
                by_index = {}
                for i,_ in usable:
                    wave[i][3]['candidate_failures'] += 1; wave[i][3]['error_type'] = type(error).__name__
            for i,(parent_id,parent_box,depth,root) in enumerate(wave):
                if layouts[i].error:
                    root['candidate_failures'] += 1; root['error_type'] = 'LayoutError'
                    continue
                result = by_index.get(i)
                if result is None: continue
                origin_x, origin_y = int(parent_box[0]*sx), int(parent_box[1]*sy)
                for child_index, (block, order) in enumerate(native_reading_order(result.blocks, scope=parent_id)):
                    # The extra pass extracts text only. Inner pictures are not
                    # source chunks, graph nodes, or inputs to Granite.
                    if normalize_layout(block.label) == 'figure':
                        continue
                    local = list(block.bbox)
                    if not valid_box(local, crops[i].width, crops[i].height):
                        root['candidate_failures'] += 1; continue
                    box = [(origin_x+local[0])/sx, (origin_y+local[1])/sy,
                           min(image.width,(origin_x+local[2])/sx), min(image.height,(origin_y+local[3])/sy)]
                    if belongs_to_page_text(box):
                        root['excluded_page_text'] += 1
                        continue
                    region_id = parent_id+'/'+str(child_index)
                    child = dict(region_id=region_id, parent_region_id=parent_id, bbox=box,
                                 label=block.label, confidence=float(getattr(block,'confidence',None) or 0),
                                 visual_depth=depth, chunk_policy='surya_layout_region',
                                 ocr_status='failed' if block.error else 'completed', **order)
                    children.append(child); root['children'].append(child)
                    if block.error:
                        root['candidate_failures'] += 1; continue
                    raw = block.html or ''
                    text = _html_text(raw)
                    if '<img' in raw.casefold() or raw.lstrip().startswith(('[','{')) or repeating_output(text):
                        child['ocr_status']='rejected'; root['candidate_rejections'] += 1; continue
                    if not text:
                        child['ocr_status']='empty'; continue
                    child.update(source_html_metadata(raw))
                    root['ocr_lines'].append(dict(text=text,bbox=box,score=child['confidence'],region_id=region_id,
                        parent_region_id=parent_id,text_source='surya_image_layout_ocr',
                        text_bbox_scope='surya_layout_region'))
    finally:
        if isinstance(manager, SuryaStreamManager): manager.visual_phase = False
    # An EOS proves only that decoding stopped. Require an independent native
    # OCR prompt on the same source pixels before publishing picture text.
    # This is transcription agreement, never a language/topic keyword filter.
    if isinstance(manager,SuryaStreamManager):
        from surya.inference.schema import BatchInputItem
        pending_lines=[(root,line) for root in roots for line in root['ocr_lines']]
        batch=[]
        for _,line in pending_lines:
            a,b,c,d=line['bbox']
            crop=sharp.crop((max(0,int(a*sx)-4),max(0,int(b*sy)-4),
                             min(sharp.width,math.ceil(c*sx)+4),min(sharp.height,math.ceil(d*sy)+4)))
            batch.append(BatchInputItem(image=frame_text_crop(crop),prompt_type='high_accuracy_bbox',
                max_tokens=8192,metadata=dict(visual_ocr=True,source_region_id=line['region_id'])))
        checks=manager.generate(batch)
        if len(checks)!=len(pending_lines): raise RuntimeError('Visual OCR verification count mismatch')
        by_id={child['region_id']:child for child in children}
        for (root,line),check in zip(pending_lines,checks):
            child=by_id[line['region_id']]
            agreement=not check.error and ''.join(_html_text(check.raw).split())==''.join(line['text'].split())
            child['ocr_validation']='surya_cross_prompt_agreement' if agreement else 'surya_cross_prompt_disagreement'
            if not agreement:
                child['ocr_status']='unresolved'
                for key in ('heading_level','heading_source','hierarchy_level_status','table_rows','table_cells',
                            'table_header_origin','table_structure_status'):
                    child.pop(key,None)
                root['candidate_rejections']+=1
                root['ocr_lines'].remove(line)
    for root in roots:
        incomplete = root['candidate_failures'] or root['candidate_rejections']
        root['status'] = ('partial' if root['ocr_lines'] else 'failed' if root['candidate_failures'] else 'unresolved') if incomplete else 'completed' if root['ocr_lines'] else 'no_text'
    metrics = dict(policy=VISUAL_OCR_POLICY, regions=len(roots), child_regions=len(children),
        excluded_page_text_regions=sum(r['excluded_page_text'] for r in roots),
        ignored_tiny_text_regions=sum(r['ignored_tiny_text'] for r in roots),
        failed=sum(bool(r['candidate_failures']) for r in roots),
        unreadable_regions=sum(r['status'] in {'partial','unresolved'} for r in roots),
        candidate_failures=sum(r['candidate_failures'] for r in roots),
        candidate_rejections=sum(r['candidate_rejections'] for r in roots),
        text_regions=sum(len(r['ocr_lines']) for r in roots), elapsed_s=round(time.perf_counter()-started,3))
    if isinstance(manager, SuryaStreamManager): metrics['generation_calls']=manager.calls[calls_before:]
    print(json.dumps(dict(event='surya_visual_ocr',status='partial' if metrics['failed'] or metrics['unreadable_regions'] else 'completed',
                         **{k:v for k,v in metrics.items() if k!='generation_calls'})),flush=True)
    return dict(regions=roots, metrics=metrics, cacheable=not metrics['failed'])


def merge_visual_ocr(page, supplemental):
    """Flatten the region tree in source order, retaining each child as a chunk."""
    roots = [dict(r,region_id=r.get('region_id',f'surya:{i}'),chunk_policy='surya_layout_region')
             for i,r in enumerate(page['layout'])]
    lines = []
    for line in page['ocr_lines']:
        item = dict(line)
        if not item.get('region_id'):
            matches = [r for r in roots if list(r['bbox']) == list(item['bbox'])]
            if len(matches) == 1: item['region_id'] = matches[0]['region_id']
        lines.append(item)
    # A large figure can overlap an already extracted page text region.
    # Deduplicate only equal text at the same location, never by text alone.
    def duplicate(candidate):
        text=' '.join(candidate.get('text','').casefold().split())
        a=candidate.get('bbox',[])
        if not text or len(a)!=4:return False
        for existing in lines:
            if text!=' '.join(existing.get('text','').casefold().split()):continue
            b=existing.get('bbox',[])
            if len(b)!=4:continue
            overlap=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
            largest=max((a[2]-a[0])*(a[3]-a[1]),(b[2]-b[0])*(b[3]-b[1]))
            if largest>0 and overlap/largest>=.8:return True
        return False
    descendants = {}
    duplicates=0
    for row in supplemental['regions']:
        region = roots[row['index']]
        if row['bbox'] != region['bbox'] or row['label'] != region['label']:
            raise ValueError('Visual OCR source region mismatch')
        region.update(visual_ocr_status=row['status'],visual_ocr_error=row['error_type'],
                      visual_ocr_candidate_failures=row.get('candidate_failures',0),
                      visual_ocr_candidate_rejections=row.get('candidate_rejections',0))
        duplicate_ids=set()
        for line in row.get('ocr_lines',[]):
            if duplicate(line):
                duplicate_ids.add(line['region_id']);duplicates+=1
            else:
                lines.append(line)
        for child in row.get('children',[]):
            if child['region_id'] in duplicate_ids:continue
            descendants.setdefault(child['parent_region_id'],[]).append(child)
    flattened = []
    def visit(region):
        region=dict(region,source_region_order=len(flattened))
        flattened.append(region)
        for child in descendants.get(region['region_id'],[]): visit(child)
    for region in roots: visit(region)
    result=dict(page,layout=flattened,ocr_lines=lines,
        metrics=dict(page.get('metrics',{}),visual_ocr=dict(supplemental['metrics'],duplicate_text_regions=duplicates),
                     elapsed_s=supplemental['metrics']['elapsed_s'],ocr_mode='single_image_layout_upgrade',
                     generation_calls=supplemental['metrics'].get('generation_calls',[])),
        visual_ocr_policy=VISUAL_OCR_POLICY,cacheable=supplemental['cacheable'])
    return result


def surya_page(image, predictor, high_resolution_image=None):
    """Normalize source OCR, including text inside previously skipped figures."""
    manager = getattr(predictor, 'manager', None)
    if isinstance(manager, SuryaStreamManager):
        manager.begin_page()
    started = time.perf_counter()
    mode = os.getenv('SURYA_OCR_MODE', 'full_page')
    if isinstance(manager, SuryaStreamManager) and mode == 'blocks':
        from surya.layout import LayoutPredictor
        layout = LayoutPredictor(manager)([image])
        if len(layout) != 1 or layout[0].error:
            raise RuntimeError('Surya could not detect source layout')
        if high_resolution_image is not None:
            from copy import deepcopy
            sx,sy=high_resolution_image.width/image.width,high_resolution_image.height/image.height
            if abs(sx/sy-1)>.01:raise ValueError('OCR images must have matching aspect ratios')
            sharp_layout=deepcopy(layout)
            for box in sharp_layout[0].bboxes:
                box.polygon=[[x*sx,y*sy] for x,y in box.polygon]
            sharp_layout[0].image_bbox=[0,0,high_resolution_image.width,high_resolution_image.height]
            result=predictor([high_resolution_image],layout_results=sharp_layout,full_page=False)[0]
            for block in result.blocks:
                block.polygon=[[x/sx,y/sy] for x,y in block.polygon]
        else:
            result = predictor([image], layout_results=layout, full_page=False)[0]
    elif mode in {'blocks', 'full_page'}:
        source_image = (high_resolution_image or image) if isinstance(manager,SuryaStreamManager) else image
        result = predictor([source_image], full_page=True)[0]
        if source_image is not image:
            sx,sy=source_image.width/image.width,source_image.height/image.height
            for block in result.blocks:
                block.polygon=[[x/sx,y/sy] for x,y in block.polygon]
    else:
        raise ValueError('SURYA_OCR_MODE must be blocks or full_page')
    regions, lines = ([], [])
    source = 'surya_layout_model' if isinstance(manager, SuryaStreamManager) and mode == 'blocks' else 'surya_full_page_model'
    for block, order in native_reading_order(result.blocks, source=source):
        bbox = [float(value) for value in block.bbox]
        score = float(getattr(block, 'confidence', None) or 0)
        region_id = f'surya:{len(regions)}'
        regions.append(dict(bbox=bbox,label=block.label,confidence=score,region_id=region_id,
                            chunk_policy='surya_layout_region',ocr_status='failed' if block.error else 'skipped' if block.skipped else 'completed',
                            source_region_order=len(regions), **order))
        if block.skipped or block.error:
            continue
        regions[-1].update(source_html_metadata(block.html))
        text = _html_text(block.html)
        if text:
            lines.append(dict(text=text,score=score,bbox=bbox,region_id=region_id))
    metrics = dict(elapsed_s=round(time.perf_counter()-started, 3),body_ocr_policy=BODY_OCR_POLICY,
                   failed_regions=sum(r['ocr_status']=='failed' for r in regions),
                   reading_order=dict(source=source, scope='page',
                       status='unresolved' if any(r['reading_order_unresolved'] for r in regions) else 'model_predicted',
                       regions=len(regions)))
    if isinstance(manager, SuryaStreamManager):
        metrics['generation_calls'] = list(manager.calls)
        metrics['ocr_mode'] = mode
    page = dict(layout=regions,ocr_lines=lines,model='surya-ocr-v2',metrics=metrics)
    from .document_structure_service import normalize_layout
    if any(normalize_layout(r['label'])=='figure' for r in regions):
        page = merge_visual_ocr(page,surya_visual_page(image,predictor,regions,reset_budget=False,
                                                   high_resolution_image=high_resolution_image))
        page['metrics']['elapsed_s'] = round(time.perf_counter()-started,3)
        page['metrics']['ocr_mode'] = mode
        if isinstance(manager,SuryaStreamManager): page['metrics']['generation_calls'] = list(manager.calls)
    else:
        page.update(visual_ocr_policy=VISUAL_OCR_POLICY,cacheable=True)
    page['cacheable'] = page.get('cacheable',True) and not metrics['failed_regions']
    return page
