import os
import sys
import django

sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from contracts.services import WorkflowService
service = WorkflowService()

try:
    print("Pushing Contract 21 (Hợp đồng dịch vụ phát triển phần mềm - TechVibe)...")
    res = service.push_to_workflow(21)
    print("RESULT:")
    print(res)
except Exception as e:
    print("ERROR:", e)
