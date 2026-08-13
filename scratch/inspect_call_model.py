import json
import os

if os.path.exists("call-model.ipynb"):
    with open("call-model.ipynb", "r", encoding="utf-8") as f:
        nb = json.load(f)

    with open("scratch/call_model_cells.txt", "w", encoding="utf-8") as out:
        out.write(f"Number of cells: {len(nb['cells'])}\n")
        for idx, cell in enumerate(nb["cells"]):
            if cell["cell_type"] == "code":
                out.write(f"=== Cell {idx} ===\n")
                out.write("".join(cell["source"]))
                out.write("\n" + "=" * 40 + "\n\n")
else:
    print("call-model.ipynb does not exist")
