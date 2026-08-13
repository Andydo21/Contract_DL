import os

for root, dirs, files in os.walk('d:\\Django_project\\RiskDL'):
    for file in files:
        if file.endswith(('.py', '.env', '.ipynb')):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if 'gemini' in content.lower() or 'generativeai' in content.lower() or 'google' in content.lower():
                    print(f"MATCH: {path}")
            except Exception:
                pass
