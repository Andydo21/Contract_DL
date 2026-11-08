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
2. Tạo **Kaggle Dataset** tên `risk-skill-data` từ 2 file `training/risk_skill/data/train.jsonl` và `valid.jsonl`,
   rồi **Add Input** dataset đó vào notebook này.
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
MAX_LEN = 4096   # the longest briefs (three provisions of ~2,400 characters) fit
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
valid_ds = Dataset.from_list([to_text(r) for r in valid_rows])
lengths = [len(tokenizer(p + c).input_ids) for p, c in zip(train_ds['prompt'][:200], train_ds['completion'][:200])]
print('tokens per sample (first 200): max', max(lengths), 'mean', sum(lengths) // len(lengths))
print(train_ds[0]['prompt'][-300:]); print(train_ds[0]['completion'][:300])
''')

code('''
# Cell 5: Train one epoch. Loss on the answer only (prompt/completion data).
from trl import SFTTrainer, SFTConfig
trainer = SFTTrainer(model=model, processing_class=tokenizer, train_dataset=train_ds, eval_dataset=valid_ds,
    args=SFTConfig(output_dir='/kaggle/working/checkpoints', max_length=MAX_LEN, completion_only_loss=True,
                   per_device_train_batch_size=2, gradient_accumulation_steps=8, num_train_epochs=1,
                   learning_rate=1e-4, lr_scheduler_type='cosine', warmup_steps=10, optim='adamw_8bit', weight_decay=0.01,
                   fp16=True, bf16=False, logging_steps=10, eval_strategy='steps', eval_steps=50,
                   per_device_eval_batch_size=2, save_strategy='steps', save_steps=50, save_total_limit=2,
                   report_to='none', seed=7))
stats = trainer.train()
print(stats)
''')

code('''
# Cell 6: Quick check on valid briefs: the adapter must answer in the target shape and follow the supplied limits.
FastLanguageModel.for_inference(model)
import re
right = 0
for row in valid_rows[:20]:
    prompt = tokenizer.apply_chat_template(row['messages'], tokenize=False, add_generation_prompt=True, enable_thinking=False)
    ids = tokenizer(prompt, return_tensors='pt').to('cuda')
    out = model.generate(**ids, max_new_tokens=700, do_sample=False)
    text = tokenizer.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True)
    try:
        answer = json.loads(text)
        legal = any(r.get('kind') == 'conflict' and r.get('law_ids') for r in answer.get('risks', []))
        right += legal == row['expect']['conflict']
    except ValueError:
        print('not JSON:', text[:200])
print(f'conflict decision right on {right}/20 valid briefs')
''')

code('''
# Cell 7: Save the adapter (a few tens of MB) and zip it for download.
model.save_pretrained('/kaggle/working/risk-skill-lora')
tokenizer.save_pretrained('/kaggle/working/risk-skill-lora')
!cd /kaggle/working && zip -qr risk-skill-lora.zip risk-skill-lora && ls -la risk-skill-lora risk-skill-lora.zip
''')

md('''
## Phục vụ adapter cùng Qwen3-8B-AWQ
Trong notebook phục vụ, thêm dataset `risk-skill-lora` làm input rồi thêm vào lệnh `vllm serve` ở cell 4:
```
'--enable-lora', '--max-lora-rank', '16',
'--lora-modules', 'risk-skill=/kaggle/input/risk-skill-lora/risk-skill-lora',
```
(đường dẫn là thư mục chứa `adapter_config.json`). Trong `.env` của web thêm:
```
QWEN_RISK_MODEL_ID=risk-skill
```
Chỉ phân tích rủi ro dùng adapter; hỏi đáp vẫn dùng model gốc. Sau đó đo lại:
`docker exec riskdl_web python -m training.risk_skill.evaluate --label qwen3-8b-lora`
''')

notebook = dict(cells=cells, metadata=dict(
    kernelspec=dict(display_name='Python 3', language='python', name='python3'),
    language_info=dict(name='python'), kaggle=dict(accelerator='nvidiaTeslaT4', isInternetEnabled=True)),
    nbformat=4, nbformat_minor=5)
out = pathlib.Path(__file__).resolve().parents[2] / 'kaggle_risk_skill_qlora.ipynb'
out.write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding='utf-8')
print(out)
