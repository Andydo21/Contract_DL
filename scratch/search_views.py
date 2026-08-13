import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('d:\\Django_project\\RiskDL\\contracts\\views.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if any(k in line.lower() for k in ['workflow', 'push', 'approve']):
        print(f"{i+1}: {line.strip()}")
