import json

def inspect():
    with open('sematic-search-26-6.ipynb', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    lines = []
    for i, cell in enumerate(data['cells']):
        source = "".join(cell.get('source', []))
        cell_type = cell['cell_type']
        summary = source.split('\n')[0] if source else ""
        lines.append(f"Cell {i:2d} | {cell_type:<8} | Length: {len(source):5d} | {summary[:80]}")
        
    with open('scripts/inspect_out.txt', 'w', encoding='utf-8') as out:
        out.write("\n".join(lines))
    print("[SUCCESS] Wrote cells listing to scripts/inspect_out.txt")

if __name__ == "__main__":
    inspect()
