import json

with open("workflow-recommendation.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)

with open("scratch/notebook_rules_cells.txt", "w", encoding="utf-8") as out:
    for idx in range(13, 20):
        cell = nb['cells'][idx]
        if cell["cell_type"] == "code":
            out.write(f"=== Cell {idx} ===\n")
            out.write("".join(cell["source"]))
            out.write("\n" + "=" * 40 + "\n\n")
