import json

def extract_cell():
    with open('sematic-search-26-6.ipynb', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Cell 26 is index 26
    source = "".join(data['cells'][26].get('source', []))
    with open('scripts/cell_26_content.py', 'w', encoding='utf-8') as out:
        out.write(source)
    print("[SUCCESS] Wrote cell 26 to scripts/cell_26_content.py")

if __name__ == "__main__":
    extract_cell()
