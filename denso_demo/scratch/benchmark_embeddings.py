import os
import sys
import time
import json
import numpy as np

os.environ['TOKENIZERS_PARALLELISM'] = 'false'
sys.stdout.reconfigure(encoding='utf-8')

test_pairs = [
    # Positive pairs (True Matches)
    {
        'category': 'Positive 1 (SOP Vibration)',
        'query': 'Mức rung cho phép trục chính máy M12 là bao nhiêu?',
        'passage': 'Mức rung cho phép trục chính máy M12 dưới 2.5 mm/s RMS. Khi độ rung nằm trong dải 2.5 - 4.5 mm/s cần theo dõi sát sao. Nếu vượt quá 4.5 mm/s, phải dừng máy ngay lập tức để kiểm tra bearing B-230.'
    },
    {
        'category': 'Positive 2 (SOP Tool & Grease)',
        'query': 'Dụng cụ cảo vòng bi và loại mỡ bôi trơn quy chuẩn cho Bearing B-230',
        'passage': 'Quy trình tiêu chuẩn căn chỉnh trục và thay thế Bearing B-230: Dùng dụng cụ chuyên dụng cảo vòng bi, tuyệt đối không dùng búa gõ trực tiếp. Tra mỡ bôi trơn chuyên dụng DENSO-HT2 với định lượng 15g.'
    },
    # Negative pairs (True Knowledge Gaps / Unrelated)
    {
        'category': 'Negative 1 (Robot Arm Drift)',
        'query': 'Robot cánh tay 6 trục tại trạm lắp ráp bị trôi tọa độ trục J3 và J5 làm rơi linh kiện',
        'passage': 'Mức rung cho phép trục chính máy M12 dưới 2.5 mm/s RMS. Khi độ rung nằm trong dải 2.5 - 4.5 mm/s cần theo dõi sát sao.'
    },
    {
        'category': 'Negative 2 (Hydraulic Press)',
        'query': 'Áp suất dầu thủy lực trên máy dập 200 tấn bị sụt giảm đột ngột từ 180 bar xuống 120 bar',
        'passage': 'Mức rung cho phép trục chính máy M12 dưới 2.5 mm/s RMS. Khi độ rung nằm trong dải 2.5 - 4.5 mm/s cần theo dõi sát sao.'
    }
]

models_to_test = [
    ('all-MiniLM-L6-v2 (Baseline)', 'sentence-transformers/all-MiniLM-L6-v2', False),
    ('paraphrase-multilingual-MiniLM-L12-v2', 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', False),
    ('multilingual-e5-small', 'intfloat/multilingual-e5-small', True)
]

from sentence_transformers import SentenceTransformer

def cosine_sim(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

results = []

for display_name, model_id, is_e5 in models_to_test:
    print(f"\n==========================================")
    print(f"BENCHMARKING: {display_name} ({model_id})")
    print(f"==========================================")
    t0 = time.time()
    try:
        model = SentenceTransformer(model_id)
        load_time = time.time() - t0
        print(f"Model loaded in {load_time:.2f}s")
    except Exception as e:
        print(f"Error loading {model_id}: {e}")
        continue

    pos_scores = []
    neg_scores = []
    latencies = []

    for pair in test_pairs:
        q = f"query: {pair['query']}" if is_e5 else pair['query']
        p = f"passage: {pair['passage']}" if is_e5 else pair['passage']

        t_enc = time.time()
        v_q = model.encode(q)
        v_p = model.encode(p)
        latencies.append((time.time() - t_enc) * 1000)

        sim = cosine_sim(v_q, v_p)
        print(f"  [{pair['category']}]: Cosine Similarity = {sim:.4f}")

        if 'Positive' in pair['category']:
            pos_scores.append(sim)
        else:
            neg_scores.append(sim)

    avg_pos = np.mean(pos_scores)
    avg_neg = np.mean(neg_scores)
    margin = avg_pos - avg_neg
    avg_latency = np.mean(latencies)

    print(f"\n--- TỔNG KẾT: {display_name} ---")
    print(f"• Độ tương đồng Positive (Signal): {avg_pos:.4f}")
    print(f"• Độ tương đồng Negative (Noise):  {avg_neg:.4f}")
    print(f"• Khoảng cách phân tách (Margin):  {margin:.4f} (Càng lớn càng nhận diện Gap chuẩn!)")
    print(f"• Độ trễ mã hóa (Avg Latency):      {avg_latency:.1f} ms")

    results.append({
        'name': display_name,
        'model_id': model_id,
        'dim': v_q.shape[0],
        'avg_pos': round(avg_pos, 4),
        'avg_neg': round(avg_neg, 4),
        'margin': round(margin, 4),
        'latency_ms': round(avg_latency, 1)
    })

print("\n\n==========================================")
print("BẢNG SO SÁNH TỔNG HỢP (BENCHMARK SUMMARY)")
print("==========================================")
print(f"{'Mô hình':<35} | {'Vector Dim':<10} | {'Positive':<10} | {'Negative':<10} | {'Margin':<10} | {'Latency':<10}")
print("-" * 95)
for r in results:
    print(f"{r['name']:<35} | {r['dim']:<10} | {r['avg_pos']:<10} | {r['avg_neg']:<10} | {r['margin']:<10} | {r['latency_ms']} ms")

# Save results json
with open(os.path.join(os.path.dirname(__file__), 'benchmark_results.json'), 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
