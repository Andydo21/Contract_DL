import os

for root, dirs, files in os.walk('d:\\Django_project\\RiskDL'):
    for file in files:
        if file.endswith(('.css', '.html', '.js')):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if 'grid' in content or 'wf-card' in content:
                    lines = content.splitlines()
                    for idx, line in enumerate(lines):
                        if 'grid' in line or 'wf-card' in line:
                            print(f"{path}:{idx+1}: {line.strip()}")
            except Exception as e:
                pass
