import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('d:\\Django_project\\RiskDL\\contracts\\services.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i in range(709, 760):
    print(f"{i+1}: {lines[i].strip()}")
