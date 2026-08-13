import json

def extract_cell():
    with open('sematic-search-26-6.ipynb', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Cell 31 is index 31
    source = "".join(data['cells'][31].get('source', []))
    with open('scripts/cell_31_content.py', 'w', encoding='utf-8') as out:
        out.write(source)
    print("[SUCCESS] Wrote cell 31 to scripts/cell_31_content.py")

if __name__ == "__main__":
    extract_cell()
