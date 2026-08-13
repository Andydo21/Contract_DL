# Cell DUY NHẤT — chạy từ đầu sau restart
import json, re, random, time, gc
import pandas as pd
import torch
from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader
from deep_translator import GoogleTranslator

# ── 1. Load CUAD ──────────────────────────────────────────────
cuad_path = "/kaggle/input/datasets/ashyou09/contract-understanding-atticus-dataset-cuad/CUAD_v1.json"
with open(cuad_path) as f:
    cuad_raw = json.load(f)

pairs = []
for contract in cuad_raw["data"]:
    for paragraph in contract["paragraphs"]:
        context = paragraph["context"]
        for qa in paragraph["qas"]:
            pairs.append({
                "query":   qa["question"],
                "passage": context,
                "label":   1 if qa["answers"] else 0
            })
df = pd.DataFrame(pairs)
print(f"✅ Loaded: {len(df):,} pairs")

# ── 2. Transform queries ───────────────────────────────────────
query_mapping = {
    "Document Name":                     ("What is the name of this contract document?",              "Tên tài liệu hợp đồng này là gì?"),
    "Parties":                           ("Who are the parties involved in this contract?",            "Các bên tham gia hợp đồng này là ai?"),
    "Agreement Date":                    ("What is the agreement date of this contract?",              "Ngày ký kết hợp đồng là khi nào?"),
    "Effective Date":                    ("What is the effective date of this contract?",              "Ngày có hiệu lực của hợp đồng là khi nào?"),
    "Expiration Date":                   ("When does this contract expire?",                           "Hợp đồng này hết hạn vào ngày nào?"),
    "Renewal Term":                      ("What is the renewal term of this contract?",                "Điều khoản gia hạn hợp đồng là gì?"),
    "Notice Period To Terminate Renewal":("What is the notice period required to terminate renewal?", "Thời gian thông báo để chấm dứt gia hạn là bao lâu?"),
    "Governing Law":                     ("What is the governing law of this contract?",               "Luật điều chỉnh hợp đồng này là luật nào?"),
    "Most Favored Nation":               ("Does this contract contain a most favored nation clause?",  "Hợp đồng có điều khoản tối huệ quốc không?"),
    "Non-Compete":                       ("Does this contract contain a non-compete clause?",          "Hợp đồng có điều khoản không cạnh tranh không?"),
    "Exclusivity":                       ("Is there an exclusivity clause in this contract?",          "Hợp đồng có điều khoản độc quyền không?"),
    "No-Solicit Of Customers":           ("Does this contract restrict solicitation of customers?",    "Hợp đồng có cấm tiếp cận khách hàng không?"),
    "Competitive Restriction Exception": ("Are there exceptions to competitive restrictions?",         "Có ngoại lệ nào cho điều khoản hạn chế cạnh tranh không?"),
    "No-Solicit Of Employees":           ("Does this contract restrict solicitation of employees?",    "Hợp đồng có cấm tuyển dụng nhân viên của bên kia không?"),
    "Non-Disparagement":                 ("Is there a non-disparagement clause in this contract?",     "Hợp đồng có điều khoản không được bôi nhọ không?"),
    "Termination For Convenience":       ("Can this contract be terminated for convenience?",          "Hợp đồng có thể chấm dứt theo ý muốn không?"),
    "Rofr/Rofo/Rofn":                   ("Is there a right of first refusal or first offer clause?",  "Hợp đồng có điều khoản quyền ưu tiên mua không?"),
    "Change Of Control":                 ("What happens upon a change of control?",                    "Điều gì xảy ra khi có thay đổi quyền kiểm soát?"),
    "Anti-Assignment":                   ("Does this contract restrict assignment?",                   "Hợp đồng có điều khoản chống chuyển nhượng không?"),
    "Revenue/Profit Sharing":            ("Is there a revenue or profit sharing clause?",              "Hợp đồng có điều khoản chia sẻ doanh thu không?"),
    "Price Restrictions":                ("Are there any price restrictions in this contract?",        "Hợp đồng có điều khoản hạn chế giá không?"),
    "Minimum Commitment":                ("What is the minimum commitment in this contract?",          "Cam kết tối thiểu trong hợp đồng là gì?"),
    "Volume Restriction":                ("Are there volume restrictions in this contract?",           "Hợp đồng có hạn chế khối lượng không?"),
    "Ip Ownership Assignment":           ("Who owns the intellectual property in this contract?",      "Ai sở hữu tài sản trí tuệ trong hợp đồng này?"),
    "Joint Ip Ownership":                ("Is there joint intellectual property ownership?",           "Hợp đồng có điều khoản đồng sở hữu tài sản trí tuệ không?"),
    "License Grant":                     ("What license is granted in this contract?",                 "Hợp đồng cấp phép sử dụng gì?"),
    "Non-Transferable License":          ("Is the license non-transferable?",                          "Giấy phép có thể chuyển nhượng không?"),
    "Affiliate License-Licensor":        ("Can the licensor extend the license to affiliates?",        "Bên cấp phép có thể mở rộng giấy phép cho công ty liên kết không?"),
    "Affiliate License-Licensee":        ("Can the licensee extend the license to affiliates?",        "Bên được cấp phép có thể mở rộng cho công ty liên kết không?"),
    "Unlimited/All-You-Can-Eat-License": ("Is there an unlimited license granted?",                   "Hợp đồng có cấp phép sử dụng không giới hạn không?"),
    "Irrevocable Or Perpetual License":  ("Is the license irrevocable or perpetual?",                 "Giấy phép có vĩnh viễn hoặc không thể thu hồi không?"),
    "Source Code Escrow":                ("Is there a source code escrow clause?",                    "Hợp đồng có điều khoản ký quỹ mã nguồn không?"),
    "Post-Termination Services":         ("Are there post-termination service obligations?",           "Có nghĩa vụ dịch vụ nào sau khi chấm dứt hợp đồng không?"),
    "Audit Rights":                      ("Does this contract include audit rights?",                  "Hợp đồng có điều khoản quyền kiểm toán không?"),
    "Uncapped Liability":                ("Is there uncapped liability in this contract?",             "Hợp đồng có trách nhiệm pháp lý không giới hạn không?"),
    "Cap On Liability":                  ("What is the cap on liability in this contract?",            "Giới hạn trách nhiệm pháp lý trong hợp đồng là bao nhiêu?"),
    "Liquidated Damages":                ("Are there liquidated damages clauses?",                     "Hợp đồng có điều khoản bồi thường thiệt hại ấn định không?"),
    "Warranty Duration":                 ("What is the warranty duration in this contract?",           "Thời hạn bảo hành trong hợp đồng là bao lâu?"),
    "Insurance":                         ("What are the insurance requirements in this contract?",     "Yêu cầu bảo hiểm trong hợp đồng là gì?"),
    "Covenant Not To Sue":               ("Is there a covenant not to sue clause?",                   "Hợp đồng có điều khoản cam kết không khởi kiện không?"),
    "Third Party Beneficiary":           ("Are there third party beneficiaries in this contract?",     "Hợp đồng có bên thụ hưởng thứ ba không?"),
}

def extract_clause_type(q):
    m = re.search(r'"([^"]+)"', q)
    return m.group(1) if m else None

rows = []
for _, row in df.iterrows():
    clause = extract_clause_type(row["query"])
    if clause not in query_mapping:
        continue
    en_q, vi_q = query_mapping[clause]
    rows.append({"query": en_q, "passage": row["passage"], "label": row["label"]})
    rows.append({"query": vi_q, "passage": row["passage"], "label": row["label"]})

df_transformed = pd.DataFrame(rows)
positives = df_transformed[df_transformed["label"]==1][["query","passage"]].copy()
positives = positives.sample(frac=1, random_state=42).reset_index(drop=True)

split    = int(len(positives) * 0.8)
train_df = positives[:split]
val_df   = positives[split:]
print(f"✅ Train: {len(train_df):,} | Val: {len(val_df):,}")

# ── 3. Dịch 500 cặp sang tiếng Việt ──────────────────────────
translator = GoogleTranslator(source='en', target='vi')
sample_vi  = train_df.sample(n=500, random_state=42).reset_index(drop=True)
vi_pairs   = []

for i, row in sample_vi.iterrows():
    try:
        query_vi   = translator.translate(row["query"][:200])
        passage_vi = translator.translate(row["passage"][:400])
        vi_pairs.append({"query": query_vi,     "passage": row["passage"]})
        vi_pairs.append({"query": query_vi,     "passage": passage_vi})
        vi_pairs.append({"query": row["query"], "passage": passage_vi})
        if i % 100 == 0:
            print(f"  Dịch {i}/500...")
            time.sleep(1)
    except:
        continue

vi_df    = pd.DataFrame(vi_pairs)
combined = pd.concat([
    train_df[["query","passage"]],
    vi_df[["query","passage"]]
], ignore_index=True).sample(frac=1, random_state=42).reset_index(drop=True)

print(f"✅ Tổng combined: {len(combined):,}")

# ── 4. Fine-tune ───────────────────────────────────────────────
os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True"
gc.collect()
torch.cuda.empty_cache()
print(f"GPU: {torch.cuda.is_available()}")

train_examples = [
    InputExample(texts=[f"query: {r['query']}", f"passage: {r['passage']}"])
    for _, r in combined.iterrows()
]

model = SentenceTransformer("intfloat/multilingual-e5-base")

BATCH_SIZE = 8  # nhỏ hơn để tránh OOM
EPOCHS     = 3

train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=BATCH_SIZE)
train_loss       = losses.MultipleNegativesRankingLoss(model=model)
warmup_steps     = int(len(train_dataloader) * EPOCHS * 0.1)

print(f"Steps/epoch : {len(train_dataloader):,}")
print(f"Total steps : {len(train_dataloader)*EPOCHS:,}")
print("Bắt đầu train...")

model.fit(
    train_objectives=[(train_dataloader, train_loss)],
    epochs=EPOCHS,
    warmup_steps=warmup_steps,
    show_progress_bar=True,
    output_path="/kaggle/working/contract-e5-v2",
    checkpoint_path="/kaggle/working/checkpoints-v2",
    checkpoint_save_steps=500,
)

print("✅ Train xong!")
