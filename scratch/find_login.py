import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('d:\\Django_project\\RiskDL\\contracts\\views.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

found = False
for i, line in enumerate(lines):
    if 'def login_user' in line:
        found = True
        for j in range(max(0, i-2), min(len(lines), i+30)):
            print(f"{j+1}: {lines[j].strip()}")
        break
if not found:
    print("def login_user not found")
