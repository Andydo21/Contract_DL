import os, sys, time, torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel
sys.stdout.reconfigure(encoding='utf-8')
os.environ['HF_HOME'] = r'D:\hf_cache'

test_cases = [
    {
        'domain': '1. Mạch Dừng Khẩn Cấp & Rơ-le An Toàn (Safety E-Stop)',
        'query': 'Sơ đồ mạch dừng khẩn cấp và rơ le an toàn DENSO',
        'pos': 'Quy trình đấu nối công tắc dừng khẩn cấp Emergency Stop Switch S1 kết hợp cụm rơ-le an toàn Safety Relay K1 ngắt nguồn động cơ máy ép tự động',
        'neg': 'Báo cáo lịch bảo trì định kỳ hệ thống điều hòa văn phòng và máy in tầng 2 tháng 8'
    },
    {
        'domain': '2. Cảm Biến & Tự Động Hóa PLC (Sensors & Actuators)',
        'query': 'Lỗi cảm biến tiệm cận quang học phát hiện phôi xi lanh',
        'pos': 'Khắc phục tín hiệu cảm biến quang sợi phát hiện vị trí phôi hành trình xi lanh khí nén SMC trạm gắp phôi tự động',
        'neg': 'Thực đơn bữa trưa nhà ăn công nhân viên công ty Denso chi nhánh Hà Nội'
    },
    {
        'domain': '3. Kiểm Tra Khuyết Tật Bề Mặt AI (Surface Defect Inspection)',
        'query': 'Thuật toán phát hiện lỗi nứt bề mặt và xước chi tiết cơ khí',
        'pos': 'Mô hình xử lý ảnh thị giác máy tính phân loại khuyết tật bề mặt sản phẩm kim loại: vết nứt vi mô, trầy xước và rỗ khí đúc',
        'neg': 'Hướng dẫn cài đặt hệ điều hành Windows và bộ gõ tiếng Việt Unikey cho văn phòng'
    }
]

models = [
    ('all-MiniLM-L6-v2 (Monolingual En)', 'sentence-transformers/all-MiniLM-L6-v2', 'minilm', 384),
    ('multilingual-e5-small (Multilingual SOTA)', 'intfloat/multilingual-e5-small', 'e5', 384),
    ('paraphrase-multilingual-MiniLM-L12-v2', 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', 'minilm_multi', 384),
]

def embed(model, tokenizer, text, mtype, is_q=False):
    if mtype == 'e5':
        text = ('query: ' if is_q else 'passage: ') + text
    inp = tokenizer(text, padding=True, truncation=True, max_length=256, return_tensors='pt')
    with torch.no_grad():
        out = model(**inp)
        if mtype == 'e5':
            mask = inp['attention_mask'].unsqueeze(-1).expand(out.last_hidden_state.size()).float()
            emb = F.normalize(torch.sum(out.last_hidden_state * mask, 1) / torch.clamp(mask.sum(1), min=1e-9), p=2, dim=1)
        else:
            emb = F.normalize(out.last_hidden_state.mean(dim=1), p=2, dim=1)
    return emb[0], len(inp['input_ids'][0])

print("=" * 85)
print("BENCHMARK THỰC TẾ TRÊN CORPUS TIẾNG VIỆT KỸ THUẬT")
print("=" * 85)

for name, mid, mtype, dim in models:
    tok = AutoTokenizer.from_pretrained(mid)
    mod = AutoModel.from_pretrained(mid)
    mod.eval()
    print(f"\n[MODEL] {name} (Dim: {dim})")
    pos_sims, neg_sims, gaps, lats, q_toks, p_toks = [], [], [], [], [], []
    for c in test_cases:
        t0 = time.time()
        q_v, q_t = embed(mod, tok, c['query'], mtype, is_q=True)
        p_v, p_t = embed(mod, tok, c['pos'], mtype, is_q=False)
        n_v, _ = embed(mod, tok, c['neg'], mtype, is_q=False)
        lat = (time.time() - t0) * 1000
        p_sim = float(torch.dot(q_v, p_v).item())
        n_sim = float(torch.dot(q_v, n_v).item())
        gap = p_sim - n_sim
        pos_sims.append(p_sim); neg_sims.append(n_sim); gaps.append(gap); lats.append(lat)
        q_toks.append(q_t); p_toks.append(p_t)
        domain_name = c['domain']
        print(f"  • {domain_name}")
        print(f"    Pos: {p_sim*100:.2f}% | Neg: {n_sim*100:.2f}% | Gap: {gap*100:+.2f}% | Tokens: Q={q_t}, P={p_t}")
    avg_p = sum(pos_sims)/len(pos_sims)*100
    avg_n = sum(neg_sims)/len(neg_sims)*100
    avg_g = sum(gaps)/len(gaps)*100
    avg_l = sum(lats)/len(lats)
    print(f"  => TỔNG KẾT {name}:")
    print(f"     Độ tương đồng Positive: {avg_p:.2f}% | Negative: {avg_n:.2f}% | Discriminative Gap: {avg_g:+.2f}% | Latency: {avg_l:.1f}ms")
