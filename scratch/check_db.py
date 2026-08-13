import os
import django
import sys

sys.path.append('d:\\Django_project\\RiskDL')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from contracts.models import ContractVersion

version = ContractVersion.objects.get(id=93)
with open('d:\\Django_project\\RiskDL\\scratch\\db_stats.txt', 'w', encoding='utf-8') as f:
    f.write(f"=== VERSION 93 CONTEXTS ===\n")
    for i, ctx in enumerate(version.contexts.all()):
        f.write(f"Page {i+1} (source={ctx.source}, confidence={ctx.relevance_score}):\n")
        f.write("-" * 40 + "\n")
        f.write(ctx.content)
        f.write("\n" + "-" * 40 + "\n")
