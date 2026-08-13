import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('d:\\Django_project\\RiskDL\\contracts\\services.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '_run_ai_analysis_via_api' in line:
        for j in range(max(0, i-5), min(len(lines), i+60)):
            print(f"{j+1}: {lines[j].strip()}")
