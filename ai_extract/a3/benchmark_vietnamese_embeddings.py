import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Load env & set cache to D drive
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
os.environ["HF_HOME"] = r"D:\hf_cache"
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
hf_token = os.environ.get("HF_TOKEN") or None

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel

test_cases = [
    {
        "domain": "1. Mạch Dừng Khẩn Cấp & Rơ-le An Toàn (Safety E-Stop)",
        "query": "Sơ đồ mạch dừng khẩn cấp và rơ le an toàn DENSO",
        "pos": "Quy trình đấu nối công tắc dừng khẩn cấp Emergency Stop Switch S1 kết hợp cụm rơ-le an toàn Safety Relay K1 ngắt nguồn động cơ máy ép tự động",
        "neg": "Báo cáo lịch bảo trì định kỳ hệ thống điều hòa văn phòng và máy in tầng 2 tháng 8"
    },
    {
        "domain": "2. Cảm Biến & Tự Động Hóa PLC (Sensors & Actuators)",
        "query": "Lỗi cảm biến tiệm cận quang học phát hiện phôi xi lanh",
        "pos": "Khắc phục tín hiệu cảm biến quang sợi phát hiện vị trí phôi hành trình xi lanh khí nén SMC trạm gắp phôi tự động",
        "neg": "Thực đơn bữa trưa nhà ăn công nhân viên công ty Denso chi nhánh Hà Nội"
    },
    {
        "domain": "3. Kiểm Tra Khuyết Tật Bề Mặt AI (Surface Defect Inspection)",
        "query": "Thuật toán phát hiện lỗi nứt bề mặt và xước chi tiết cơ khí",
        "pos": "Mô hình xử lý ảnh thị giác máy tính phân loại khuyết tật bề mặt sản phẩm kim loại: vết nứt vi mô, trầy xước và rỗ khí đúc",
        "neg": "Hướng dẫn cài đặt hệ điều hành Windows và bộ gõ tiếng Việt Unikey cho văn phòng"
    }
]

models_to_test = [
    {
        "name": "all-MiniLM-L6-v2 (Monolingual English)",
        "model_id": "sentence-transformers/all-MiniLM-L6-v2",
        "type": "minilm",
        "dim": 384
    },
    {
        "name": "multilingual-e5-small (Multilingual SOTA)",
        "model_id": "intfloat/multilingual-e5-small",
        "type": "e5",
        "dim": 384
    },
    {
        "name": "paraphrase-multilingual-MiniLM-L12-v2",
        "model_id": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "type": "minilm_multi",
        "dim": 384
    }
]

# Check if bge-m3 is already downloaded or can be tested
try:
    models_to_test.append({
        "name": "BAAI/bge-m3 (FlagEmbedding Multi-Function)",
        "model_id": "BAAI/bge-m3",
        "type": "bge_m3",
        "dim": 1024
    })
except Exception:
    pass

print("=" * 80)
print("  BENCHMARK EMBEDDING MODELS CHO CORPUS TIẾNG VIỆT & TÀI LIỆU KỸ THUẬT NHÀ MÁY")
print("=" * 80)

def embed_text(model, tokenizer, text, m_type, is_query=False):
    if m_type == "e5":
        prefix = "query: " if is_query else "passage: "
        text = prefix + text
    
    inputs = tokenizer(text, padding=True, truncation=True, max_length=256, return_tensors='pt')
    with torch.no_grad():
        outputs = model(**inputs)
        if m_type == "e5":
            mask = inputs['attention_mask'].unsqueeze(-1).expand(outputs.last_hidden_state.size()).float()
            sum_emb = torch.sum(outputs.last_hidden_state * mask, 1)
            sum_mask = torch.clamp(mask.sum(1), min=1e-9)
            emb = F.normalize(sum_emb / sum_mask, p=2, dim=1)
        elif m_type == "bge_m3":
            # CLS token representation normalized
            emb = outputs.last_hidden_state[:, 0]
            emb = F.normalize(emb, p=2, dim=1)
        else:
            emb = outputs.last_hidden_state.mean(dim=1)
            emb = F.normalize(emb, p=2, dim=1)
    return emb[0], len(inputs['input_ids'][0])

benchmark_results = {}

for m_cfg in models_to_test:
    m_name = m_cfg["name"]
    m_id = m_cfg["model_id"]
    m_type = m_cfg["type"]
    print(f"\n[Benchmarking] Đang nạp model: {m_name} ({m_id})...")
    
    t0 = time.time()
    try:
        tok = AutoTokenizer.from_pretrained(m_id, token=hf_token)
        mod = AutoModel.from_pretrained(m_id, token=hf_token)
        mod.eval()
    except Exception as err:
        print(f"  --> Bỏ qua {m_name} do chưa tải về hoặc lỗi: {err}")
        continue
    load_time = time.time() - t0
    
    results_list = []
    total_latency = 0.0
    total_tokens_q = 0
    total_tokens_p = 0
    
    for case in test_cases:
        t_start = time.time()
        q_emb, q_tokens = embed_text(mod, tok, case["query"], m_type, is_query=True)
        pos_emb, p_tokens = embed_text(mod, tok, case["pos"], m_type, is_query=False)
        neg_emb, _ = embed_text(mod, tok, case["neg"], m_type, is_query=False)
        t_elapsed = (time.time() - t_start) * 1000  # ms
        
        sim_pos = float(torch.dot(q_emb, pos_emb).item())
        sim_neg = float(torch.dot(q_emb, neg_emb).item())
        gap = sim_pos - sim_neg
        
        total_latency += t_elapsed
        total_tokens_q += q_tokens
        total_tokens_p += p_tokens
        
        results_list.append({
            "domain": case["domain"],
            "sim_pos": round(sim_pos, 4),
            "sim_neg": round(sim_neg, 4),
            "gap": round(gap, 4),
            "q_tokens": q_tokens,
            "p_tokens": p_tokens
        })
    
    avg_pos = sum(r["sim_pos"] for r in results_list) / len(results_list)
    avg_neg = sum(r["sim_neg"] for r in results_list) / len(results_list)
    avg_gap = avg_pos - avg_neg
    avg_latency = total_latency / len(results_list)
    
    benchmark_results[m_name] = {
        "dim": m_cfg["dim"],
        "avg_pos": round(avg_pos, 4),
        "avg_neg": round(avg_neg, 4),
        "avg_gap": round(avg_gap, 4),
        "avg_latency_ms": round(avg_latency, 2),
        "avg_q_tokens": round(total_tokens_q / len(results_list), 1),
        "avg_p_tokens": round(total_tokens_p / len(results_list), 1),
        "cases": results_list
    }

print("\n" + "=" * 80)
print("                           KẾT QUẢ BENCHMARK TỔNG HỢP")
print("=" * 80)
header = f"{'Model':<38} | {'Dim':<5} | {'Pos Sim':<8} | {'Neg Sim':<8} | {'Gap (Disc)':<10} | {'Latency':<8} | {'Tok Len (Q/P)'}"
print(header)
print("-" * 105)

for name, res in benchmark_results.items():
    tok_str = f"{res['avg_q_tokens']}/{res['avg_p_tokens']}"
    row = f"{name:<38} | {res['dim']:<5} | {res['avg_pos']:<8} | {res['avg_neg']:<8} | {res['avg_gap']:<10} | {res['avg_latency_ms']:<6}ms | {tok_str}"
    print(row)

print("=" * 80)
for name, res in benchmark_results.items():
    print(f"\nChi tiết từng Test Case cho: {name}")
    for c in res["cases"]:
        print(f"  • {c['domain']}")
        print(f"    - Positive Match: {c['sim_pos'] * 100:.1f}% | Negative Match: {c['sim_neg'] * 100:.1f}% | Gap: {c['gap'] * 100:+.1f}% (Tokens: Q={c['q_tokens']}, P={c['p_tokens']})")
