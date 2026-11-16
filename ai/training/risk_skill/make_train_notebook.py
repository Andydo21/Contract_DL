"""Writes kaggle_risk_skill_qlora.ipynb: QLoRA training of Qwen3-8B on the risk-skill data (one Kaggle T4)."""
import json
import pathlib

cells = []


def md(text):
    cells.append(dict(cell_type='markdown', metadata={}, source=text.strip('\n').splitlines(keepends=True)))


def code(text):
    cells.append(dict(cell_type='code', metadata={}, execution_count=None, outputs=[],
                      source=text.strip('\n').splitlines(keepends=True)))


md('''
# Train the contract risk-reading skill: QLoRA on Qwen3-8B (Kaggle T4)

Dạy Qwen3-8B **kỹ năng** đọc điều khoản hợp đồng cùng các điều luật được đưa vào brief: so con số, nhận ra quy định
cho phép thỏa thuận khác, phân biệt trái quy định với mơ hồ, chép đúng câu trích. Luật không nằm trong trọng số:
dữ liệu có các cặp "luật đổi số" nên model phải đọc luật trong brief.

Kết quả là một **LoRA adapter** (vài chục MB). Notebook phục vụ (`kaggle_qwen3_8b_awq_serving.ipynb`) nạp adapter này
bên cạnh Qwen3-8B-AWQ; tốc độ không đổi.

### Trước khi chạy
1. **Accelerator**: GPU T4 (1 GPU là đủ). **Internet**: ON.
2. Tạo **Kaggle Dataset** tên `risk-skill-data` bằng cách tải lên `ai/training/risk_skill/data/risk-skill-data.zip`
   (chứa `train.jsonl` và `valid.jsonl`, dữ liệu phiên bản 3), rồi **Add Input** dataset đó vào notebook này.
   Khi dữ liệu đổi, tạo **New Version** cho dataset rồi chạy lại notebook.
3. Chạy lần lượt. Train 1 epoch (~2.700 mẫu) mất khoảng 2–3 giờ trên T4.

### Sau khi train
Tải `/kaggle/working/risk-skill-lora.zip` (hoặc **Save Version** để thành output), tạo dataset `risk-skill-lora` từ thư
mục adapter, rồi thêm vào notebook phục vụ (hướng dẫn ở cuối notebook này).
''')

code('''
# Cell 1: Packages. Unsloth runs QLoRA on a T4 (fp16) with less memory and about twice the speed of plain PEFT.
!pip install -q unsloth
import torch
print(torch.__version__, torch.cuda.get_device_name(0))
''')

code('''
# Cell 2: Data. Each record holds the chat messages exactly as the service sends them and the target JSON answer.
import glob, json
def find(name):
    hits = glob.glob(f'/kaggle/input/**/{name}', recursive=True)
    if not hits:
        raise FileNotFoundError(f'{name} not found: add the risk-skill-data dataset as input.')
    return hits[0]
def load(name):
    return [json.loads(line) for line in open(find(name), encoding='utf-8')]
train_rows, valid_rows = load('train.jsonl'), load('valid.jsonl')
print(len(train_rows), 'train /', len(valid_rows), 'valid')
print(train_rows[0]['messages'][1]['content'][:600])
''')

code('''
# Cell 3: Model. Qwen3-8B in 4-bit for training; LoRA on all attention and MLP projections.
from unsloth import FastLanguageModel
MAX_LEN = 4352   # data v4: the longest brief + answer is ~4,050 tokens with the chat template; none is cut
model, tokenizer = FastLanguageModel.from_pretrained('unsloth/Qwen3-8B-unsloth-bnb-4bit', max_seq_length=MAX_LEN,
                                                     load_in_4bit=True, dtype=None)
model = FastLanguageModel.get_peft_model(model, r=16, lora_alpha=32, lora_dropout=0, bias='none',
    target_modules=['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj'],
    use_gradient_checkpointing='unsloth', random_state=7)
''')

code('''
# Cell 4: Prompt/completion text. The prompt is the chat template with thinking off, exactly what the server builds for
# the request (it ends with an empty <think></think>); only the answer is learned.
from datasets import Dataset
def to_text(row):
    prompt = tokenizer.apply_chat_template(row['messages'], tokenize=False, add_generation_prompt=True, enable_thinking=False)
    completion = json.dumps(row['target'], ensure_ascii=False) + tokenizer.eos_token
    return dict(prompt=prompt, completion=completion)
train_ds = Dataset.from_list([to_text(r) for r in train_rows])
valid_ds = Dataset.from_list([to_text(r) for r in valid_rows[:60]])   # a sample keeps evaluation cheap
lengths = [len(tokenizer(p + c).input_ids) for p, c in zip(train_ds['prompt'][:200], train_ds['completion'][:200])]
print('tokens per sample (first 200): max', max(lengths), 'mean', sum(lengths) // len(lengths))
print(train_ds[0]['prompt'][-300:]); print(train_ds[0]['completion'][:300])
''')

code('''
# Cell 5: Train two epochs (one left the first adapter under-trained). Loss on the answer only.
from trl import SFTTrainer, SFTConfig
trainer = SFTTrainer(model=model, processing_class=tokenizer, train_dataset=train_ds, eval_dataset=valid_ds,
    args=SFTConfig(output_dir='/kaggle/working/checkpoints', max_length=MAX_LEN, completion_only_loss=True,
                   per_device_train_batch_size=1, gradient_accumulation_steps=16, num_train_epochs=2,
                   learning_rate=2e-4, lr_scheduler_type='cosine', warmup_steps=10, optim='adamw_8bit', weight_decay=0.01,
                   fp16=True, bf16=False, logging_steps=10, eval_strategy='steps', eval_steps=100,
                   per_device_eval_batch_size=1, save_strategy='steps', save_steps=100, save_total_limit=2,
                   report_to='none', seed=7))
stats = trainer.train()
print(stats)
''')

code('''
# Cell 6: Quick check on valid briefs, as the service checks an answer: a conflict counts only when it cites the
# right provision (L-number) and its law quote is that provision's words; no conflict where none is expected.
FastLanguageModel.for_inference(model)
plain = lambda s: ' '.join((s or '').split()).casefold()
decided, cited_right, quoted, n = 0, 0, 0, 40
for row in valid_rows[:n]:
    prompt = tokenizer.apply_chat_template(row['messages'], tokenize=False, add_generation_prompt=True, enable_thinking=False)
    ids = tokenizer(prompt, return_tensors='pt').to('cuda')
    out = model.generate(**ids, max_new_tokens=1600, do_sample=False)   # the service allows 1,600 tokens
    text = tokenizer.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True)
    try:
        answer = json.loads(text)
    except ValueError:
        print('not JSON:', text[:200])
        continue
    conflicts = [r for r in answer.get('risks', []) if r.get('kind') == 'conflict' and r.get('law_ids')]
    wanted = {i for r in row['target']['risks'] if r.get('kind') == 'conflict' for i in r.get('law_ids', [])}
    decided += bool(conflicts) == bool(wanted)
    if wanted:
        cited_right += wanted <= {i for r in conflicts for i in r['law_ids']}
        quoted += all(plain(r.get('law_quote')) in plain(row['laws'][int(r['law_ids'][0][1:]) - 1]['text'])
                      for r in conflicts) and bool(conflicts)
expected = sum(any(r.get('kind') == 'conflict' for r in row['target']['risks']) for row in valid_rows[:n])
print(f'conflict or not right: {decided}/{n} | right provision cited: {cited_right}/{expected} | '
      f'law quote word for word in the cited provision: {quoted}/{expected}')
''')

code('''
# Cell 7: Save the adapter (a few tens of MB) and zip it for download.
model.save_pretrained('/kaggle/working/risk-skill-lora')
tokenizer.save_pretrained('/kaggle/working/risk-skill-lora')
!cd /kaggle/working && zip -qr risk-skill-lora.zip risk-skill-lora && ls -la risk-skill-lora risk-skill-lora.zip
''')

md('''
## Phục vụ adapter cùng Qwen3-8B-AWQ
Tạo dataset `risk-skill-lora` từ `risk-skill-lora.zip`, rồi thêm nó làm **input** của notebook phục vụ
`ai/deploy/kaggle/kaggle_qwen3_8b_awq_serving.ipynb`. Notebook phục vụ tự tìm `adapter_config.json` và chạy vLLM với
`--enable-lora`, phục vụ adapter dưới tên `risk-skill` (không cần sửa lệnh). Trong `.env` của web thêm:
```
QWEN_RISK_MODEL_ID=risk-skill
```
Chỉ phân tích rủi ro dùng adapter; hỏi đáp vẫn dùng model gốc. Sau đó đo lại:
`docker exec riskdl_web python -m ai.training.risk_skill.evaluate --label qwen3-8b-lora`
(so với `--label qwen3-8b-base` chạy trước khi train; xem các mục `holdout`, `real_law`, `governing_absent`, `amended_law`).
''')

notebook = dict(cells=cells, metadata=dict(
    kernelspec=dict(display_name='Python 3', language='python', name='python3'),
    language_info=dict(name='python'), kaggle=dict(accelerator='nvidiaTeslaT4', isInternetEnabled=True)),
    nbformat=4, nbformat_minor=5)
out = pathlib.Path(__file__).resolve().parent / 'kaggle_risk_skill_qlora.ipynb'
out.write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding='utf-8')
print(out)
