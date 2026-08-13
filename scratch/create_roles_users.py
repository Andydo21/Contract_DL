import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from contracts.models import Role, User

roles_to_create = [
    {"name": "FINANCE", "desc": "Finance review and budget check"},
    {"name": "TECHNICAL", "desc": "Technical validation and IT architecture review"},
    {"name": "SECURITY", "desc": "Information security and cybersecurity review"},
    {"name": "COMPLIANCE", "desc": "Compliance with local/international laws and regulations"},
    {"name": "PROCUREMENT", "desc": "Procurement and vendor management review"},
    {"name": "EXECUTIVE", "desc": "Board of directors and executive leadership approval"},
]

print("Initializing Roles...")
role_objs = {}
for r_info in roles_to_create:
    role, created = Role.objects.get_or_create(
        role_name=r_info["name"],
        defaults={"description": r_info["desc"]}
    )
    role_objs[r_info["name"]] = role
    if created:
        print(f"Created Role: {r_info['name']}")
    else:
        print(f"Role already exists: {r_info['name']}")

users_to_create = [
    {"username": "user_finance", "role": "FINANCE"},
    {"username": "user_tech", "role": "TECHNICAL"},
    {"username": "user_security", "role": "SECURITY"},
    {"username": "user_compliance", "role": "COMPLIANCE"},
    {"username": "user_procurement", "role": "PROCUREMENT"},
    {"username": "user_executive", "role": "EXECUTIVE"},
]

print("\nInitializing Users...")
for u_info in users_to_create:
    role = role_objs.get(u_info["role"])
    user, created = User.objects.get_or_create(
        username=u_info["username"],
        defaults={
            "role": role,
            "email": f"{u_info['username']}@company.com",
            "is_staff": True
        }
    )
    if created:
        user.set_password("password123")
        user.save()
        print(f"Created User: {u_info['username']} (Role: {u_info['role']})")
    else:
        # Update role if already exists
        user.role = role
        user.save()
        print(f"User already exists, updated role: {u_info['username']} (Role: {u_info['role']})")

print("\nDone initializing roles and users!")
