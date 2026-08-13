for query, passage in test_cases:
    q1 = model_v1.encode(f"query: {query}",   normalize_embeddings=True)
    p1 = model_v1.encode(f"passage: {passage}", normalize_embeddings=True)
    s1 = float(q1 @ p1)

    q2 = model_v2.encode(f"query: {query}",   normalize_embeddings=True)
    p2 = model_v2.encode(f"passage: {passage}", normalize_embeddings=True)
    s2 = float(q2 @ p2)

    diff = s2 - s1
    flag = "✅" if diff > 0 else "❌"
    print(f"{query:<35} {s1:>6.3f} {s2:>6.3f}  {flag} {diff:>+.3f}")