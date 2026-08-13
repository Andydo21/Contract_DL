import json

def extract_notebook(ipynb_path, output_py_path):
    try:
        with open(ipynb_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
        
        code_lines = []
        for i, cell in enumerate(notebook.get('cells', [])):
            if cell.get('cell_type') == 'code':
                source = cell.get('source', '')
                code_lines.append(f"# {'='*20} CELL {i} {'='*20}")
                if isinstance(source, list):
                    code_lines.extend(source)
                else:
                    code_lines.append(source)
                code_lines.append("\n\n")
        
        with open(output_py_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(code_lines))
        print(f"Extracted {ipynb_path} -> {output_py_path}")
    except Exception as e:
        print(f"Error extracting {ipynb_path}: {e}")

if __name__ == '__main__':
    extract_notebook('d:\\Django_project\\RiskDL\\dynamic-workflow-builder.ipynb', 'd:\\Django_project\\RiskDL\\scratch\\dynamic_workflow_builder.py')
    extract_notebook('d:\\Django_project\\RiskDL\\workflow-recommendation.ipynb', 'd:\\Django_project\\RiskDL\\scratch\\workflow_recommendation.py')
