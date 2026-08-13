from sentence_transformers import SentenceTransformer

model_v1 = SentenceTransformer("d90nqm/contract-search-e5")
model_v2 = SentenceTransformer("d90nqm/contract-search-e5-v2")

test_cases = [
    ("governing law",             "This Agreement shall be governed by the laws of Illinois."),
    ("luật điều chỉnh hợp đồng", "This Agreement shall be governed by the laws of Illinois."),
    ("điều khoản chấm dứt",      "Either party may terminate this Agreement upon 30 days notice."),
    ("payment terms",             "Payment shall be made within 30 days of invoice date."),
    ("bảo mật thông tin",        "Each party agrees to maintain confidentiality for 5 years."),
    ("thời hạn bảo hành",        "The warranty period is 12 months from the date of delivery."),
]

print(f"{'Query':<35} {'v1':>6} {'v2':>6} {'Tăng':>7}")
print("-" * 60)

for query, passage in test_cases:
    s1 = float(model_v1.encode([f"query: {query}"], normalize_embeddings=True) @
               model_v1.encode([f"passage: {passage}"], normalize_embeddings=True).T)
    s2 = float(model_v2.encode([f"query: {query}"], normalize_embeddings=True) @
               model_v2.encode([f"passage: {passage}"], normalize_embeddings=True).T)
    diff = s2 - s1
    flag = "✅" if diff > 0 else "❌"
    print(f"{query:<35} {s1:>6.3f} {s2:>6.3f}  {flag} {diff:>+.3f}")