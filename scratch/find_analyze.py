import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('d:\\Django_project\\RiskDL\\contracts\\views.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i in range(300, 360):
    print(f"{i+1}: {lines[i].strip()}")
