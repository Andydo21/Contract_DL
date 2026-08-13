import os
import django
import sys

sys.path.append('d:\\Django_project\\RiskDL')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from contracts.models import User, Role

print("=== USERS ===")
for u in User.objects.all():
    role_name = u.role.role_name if u.role else "None"
    print(f"ID: {u.id}, Username: {u.username}, Role: {role_name}, Superuser: {u.is_superuser}")
