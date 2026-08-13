import chromadb, gradio as gr
from sentence_transformers import SentenceTransformer

model_ft = SentenceTransformer("d90nqm/contract-search-e5-v2")

# Chunk theo section
import re
def chunk_by_section(text):
    matches = list(re.finditer(r'\d+\.\d+\s+\w', text))
    chunks  = []
    for i, match in enumerate(matches):
        start = match.start()
        end   = matches[i+1].start() if i+1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if len(chunk.split()) >= 5:
            chunks.append(chunk)
    return chunks

sample_contract = cuad_raw["data"][0]
contract_name   = sample_contract["title"]
full_text       = " ".join([p["context"] for p in sample_contract["paragraphs"]])
chunks_sec      = chunk_by_section(full_text)

# Index
client = chromadb.Client()
try:
    client.delete_collection("contract_chunks")
except:
    pass
collection = client.create_collection("contract_chunks")

embeddings = model_ft.encode(
    [f"passage: {c}" for c in chunks_sec],
    normalize_embeddings=True,
    show_progress_bar=True
).tolist()

collection.add(
    embeddings=embeddings,
    documents=chunks_sec,
    ids=[f"sec_{i}" for i in range(len(chunks_sec))],
    metadatas=[{"chunk_index": i} for i in range(len(chunks_sec))]
)
print(f"✅ Indexed {len(chunks_sec)} sections với model v2")

# Demo
def search_final(query: str, top_k: int = 3):
    if not query.strip():
        return "⚠️ Vui lòng nhập câu hỏi"
    q_emb   = model_ft.encode([f"query: {query}"], normalize_embeddings=True).tolist()
    results = collection.query(query_embeddings=q_emb, n_results=top_k)
    output  = f"### Kết quả cho: *\"{query}\"*\n\n📄 `{contract_name}`\n\n---\n"
    for i, (doc, dist) in enumerate(zip(results["documents"][0], results["distances"][0])):
        score  = round(1 - dist, 3)
        bar    = "█" * int(score * 20)
        sec_no = results["metadatas"][0][i]["chunk_index"] + 1
        output += f"**Section #{sec_no}** · score: `{score}` {bar}\n\n> {doc[:500]}\n\n---\n"
    return output

gr.Interface(
    fn=search_final,
    inputs=[
        gr.Textbox(label="Câu hỏi (tiếng Việt hoặc tiếng Anh)",
                   placeholder="VD: governing law / điều khoản chấm dứt / payment terms",
                   lines=2),
        gr.Slider(1, 5, value=3, step=1, label="Số đoạn trả về")
    ],
    outputs=gr.Markdown(label="Kết quả"),
    title="📄 Contract Content Search v2",
    description="Model v2 — fine-tuned với data EN + VI · Score > 0.7",
    examples=[
        ["governing law", 3],
        ["luật điều chỉnh hợp đồng", 3],
        ["payment terms", 3],
        ["điều khoản chấm dứt hợp đồng", 3],
        ["bảo mật thông tin", 3],
        ["warranty duration", 3],
        ["thời hạn bảo hành", 3],
    ]
).launch(share=True)