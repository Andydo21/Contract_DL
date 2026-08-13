import json
import os

if os.path.exists("dynamic-workflow-builder.ipynb"):
    with open("dynamic-workflow-builder.ipynb", "r", encoding="utf-8") as f:
        nb = json.load(f)

    with open("scratch/dynamic_workflow_cells.txt", "w", encoding="utf-8") as out:
        out.write(f"Number of cells: {len(nb['cells'])}\n")
        for idx, cell in enumerate(nb["cells"]):
            if cell["cell_type"] == "code":
                out.write(f"=== Cell {idx} ===\n")
                out.write("".join(cell["source"]))
                out.write("\n" + "=" * 40 + "\n\n")
else:
    print("dynamic-workflow-builder.ipynb does not exist")
