with open('d:\\Django_project\\RiskDL\\contracts\\static\\contracts\\css\\workflow_board.css', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'card' in line or 'grid' in line:
        print(f"{i+1}: {line.strip()}")
