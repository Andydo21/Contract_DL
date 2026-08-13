import os
import sys

for root, dirs, files in os.walk('d:\\Django_project\\RiskDL'):
    for file in files:
        if file.endswith('.py') and 'venv' not in root:
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if 'create_superuser' in content or 'create_user' in content or 'User.objects.create' in content:
                    print(f"MATCH: {path}")
            except Exception:
                pass
