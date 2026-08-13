import json
import sys

def extract_notebook(ipynb_path, py_path):
    with open(ipynb_path, 'r', encoding='utf-8') as f:
        nb = json.load(f)
    
    code_lines = []
    for cell in nb.get('cells', []):
        if cell.get('cell_type') == 'code':
            source = cell.get('source', [])
            code_lines.append(f"# --- CELL ---\n")
            if isinstance(source, list):
                code_lines.extend(source)
            else:
                code_lines.append(source)
            code_lines.append("\n\n")
            
    with open(py_path, 'w', encoding='utf-8') as f:
        f.writelines(code_lines)
    print(f"Extracted {ipynb_path} to {py_path}")

if __name__ == "__main__":
    extract_notebook("dynamic-workflow-builder.ipynb", "scratch/dynamic_workflow_builder.py")
    extract_notebook("workflow-recommendation.ipynb", "scratch/workflow_recommendation.py")
