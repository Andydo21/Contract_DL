import json

def extract_cell():
    with open('sematic-search-26-6.ipynb', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Cell 32 is index 32
    source = "".join(data['cells'][32].get('source', []))
    with open('scripts/cell_32_content.py', 'w', encoding='utf-8') as out:
        out.write(source)
    print("[SUCCESS] Wrote cell 32 to scripts/cell_32_content.py")

if __name__ == "__main__":
    extract_cell()
