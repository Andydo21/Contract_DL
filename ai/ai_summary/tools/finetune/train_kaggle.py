# Kaggle notebook (GPU T4, a session WITHOUT the vLLM install from kaggle_notebook.py: vLLM swaps torch).
# LoRA fine-tune of a small Qwen on finetune/data/*.jsonl, merge, and push to Hugging Face.
#
# Before running:
#   1. Upload ai_summary/finetune/data/train.jsonl and dev.jsonl as a Kaggle Dataset and add it to this notebook.
#   2. Add a Kaggle secret HF_TOKEN with *write* access (Add-ons -> Secrets).
#   3. Set HF_REPO to "<your-hf-username>/<model-name>".
#
# Cell 1 — install, then restart the kernel (Run -> Restart) before Cell 2
# !pip install -q "peft>=0.13" "huggingface_hub>=0.25"
# Kaggle preinstalls torchao 0.10; recent peft finds it and refuses anything below 0.16. LoRA in fp16
# does not use torchao, so remove it.
# !pip uninstall -y -q torchao

# Cell 2 — train (on a fresh kernel: the two settings below must exist before torch is imported)
import os
# One GPU: with two visible, Trainer wraps the model in DataParallel, which gathers gradients on GPU 0
# and runs out of memory there.
os.environ['CUDA_VISIBLE_DEVICES'] = '0'
os.environ['PYTORCH_ALLOC_CONF'] = 'expandable_segments:True'
import glob
import json
import random
import time

import torch
from kaggle_secrets import UserSecretsClient
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments

BASE = 'Qwen/Qwen3-1.7B'
HF_REPO = 'phamthanhfd/contract-summary-qwen3-1.7b'
# Logits over a ~152k vocabulary dominate memory (sequence x vocab, plus their gradient); 4096 tokens fits
# a 16 GB T4 with the 1.7B model. Median sample is ~1.5k tokens; longer ones are skipped and counted below.
MAX_LEN = 4096
EPOCHS, LR = 1, 2e-4

train_path = glob.glob('/kaggle/input/**/train.jsonl', recursive=True)[0]
dev_path = glob.glob('/kaggle/input/**/dev.jsonl', recursive=True)[0]
tokenizer = AutoTokenizer.from_pretrained(BASE)
tokenizer.pad_token = tokenizer.pad_token or tokenizer.eos_token
END = '<|im_end|>'


def encode(row):
    # Same template vLLM applies at serving time (chat_template_kwargs enable_thinking=False), so the
    # student learns exactly the token sequence it will be asked to continue.
    prompt = tokenizer.apply_chat_template(row['prompt'], tokenize=False, add_generation_prompt=True, enable_thinking=False)
    prompt_ids = tokenizer(prompt, add_special_tokens=False).input_ids
    answer_ids = tokenizer(row['completion'] + END, add_special_tokens=False).input_ids
    if len(prompt_ids) + len(answer_ids) > MAX_LEN:
        return None
    return dict(input_ids=prompt_ids + answer_ids, labels=[-100] * len(prompt_ids) + answer_ids)


def load(path):
    rows = [encode(json.loads(line)) for line in open(path, encoding='utf-8')]
    kept = [r for r in rows if r]
    print(f'{path}: {len(kept)}/{len(rows)} samples within {MAX_LEN} tokens')
    return kept


train, dev = load(train_path), load(dev_path)[:60]


def collate(batch):
    width = max(len(b['input_ids']) for b in batch)
    pad = lambda seq, value: seq + [value] * (width - len(seq))
    return dict(input_ids=torch.tensor([pad(b['input_ids'], tokenizer.pad_token_id) for b in batch]),
                labels=torch.tensor([pad(b['labels'], -100) for b in batch]),
                attention_mask=torch.tensor([pad([1] * len(b['input_ids']), 0) for b in batch]))


model = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.float16, device_map={'': 0})
model.gradient_checkpointing_enable()
model.enable_input_require_grads()
model.config.use_cache = False
model = get_peft_model(model, LoraConfig(
    r=16, lora_alpha=32, lora_dropout=0.05, task_type='CAUSAL_LM',
    target_modules=['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj']))
for parameter in model.parameters():  # fp16 base, fp32 adapters: the grad scaler cannot unscale fp16 grads
    if parameter.requires_grad:
        parameter.data = parameter.data.float()
model.print_trainable_parameters()

random.Random(0).shuffle(train)
trainer = Trainer(
    model=model, train_dataset=train, eval_dataset=dev, data_collator=collate,
    args=TrainingArguments(
        output_dir='/kaggle/working/lora', per_device_train_batch_size=1, gradient_accumulation_steps=8,
        num_train_epochs=EPOCHS, learning_rate=LR, lr_scheduler_type='cosine', warmup_ratio=0.03,
        fp16=True, logging_steps=10, eval_strategy='steps', eval_steps=100, per_device_eval_batch_size=1,
        save_strategy='no', report_to='none', remove_unused_columns=False))
started = time.time()
trainer.train()
print(f'trained in {(time.time() - started) / 60:.1f} min; dev loss {trainer.evaluate()["eval_loss"]:.4f}')

# Cell 3 — sanity check on dev prompts: the reply must be JSON with every schema key
model.eval()
model.config.use_cache = True
for row in [json.loads(line) for line in open(dev_path, encoding='utf-8')][:3]:
    prompt = tokenizer.apply_chat_template(row['prompt'], tokenize=False, add_generation_prompt=True, enable_thinking=False)
    ids = tokenizer(prompt, return_tensors='pt', add_special_tokens=False).to(0)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=1500, do_sample=False)
    reply = tokenizer.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True)
    try:
        parsed, expected = json.loads(reply), json.loads(row['completion'])
        same = sum(parsed.get(k) == v for k, v in expected.items())
        print(f'valid JSON, {same}/{len(expected)} fields identical to the label')
    except ValueError:
        print('INVALID JSON:', reply[:300])

# Cell 4 — merge and push (vLLM then serves the repo like any base model)
merged = model.merge_and_unload()
merged = merged.half()
merged.save_pretrained('/kaggle/working/merged', safe_serialization=True)
tokenizer.save_pretrained('/kaggle/working/merged')
from huggingface_hub import HfApi
api = HfApi(token=UserSecretsClient().get_secret('HF_TOKEN'))
api.create_repo(HF_REPO, private=True, exist_ok=True)
api.upload_folder(folder_path='/kaggle/working/merged', repo_id=HF_REPO)
print('pushed', HF_REPO, '- serve it as NEW_CANDIDATE in kaggle_notebook.py Cell 4')
