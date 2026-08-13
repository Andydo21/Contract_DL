import os
import django
import sys

sys.path.append('d:\\Django_project\\RiskDL')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from contracts.models import Contract

sys.stdout.reconfigure(encoding='utf-8')

print("=== CONTRACTS ===")
for c in Contract.objects.all()[:25]:
    print(f"ID: {c.id}, Code: {c.contract_code}, Title: {c.title}, Status: {c.status}")
