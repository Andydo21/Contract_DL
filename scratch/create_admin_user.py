import os
import django
import sys

# Get project root (parent directory of scratch)
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root_dir)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from contracts.models import Role

User = get_user_model()

def create_admin():
    username = "admin"
    password = "password123"
    
    # Get or create ADMIN and MANAGER roles
    admin_role, _ = Role.objects.get_or_create(role_name='ADMIN')
    manager_role, _ = Role.objects.get_or_create(role_name='MANAGER')
    
    user = User.objects.filter(username=username).first()
    if user:
        print(f"User '{username}' already exists. Updating password and roles...")
        user.set_password(password)
        user.is_superuser = True
        user.is_staff = True
        user.role = admin_role
        user.save()
    else:
        print(f"Creating superuser '{username}'...")
        user = User.objects.create_superuser(
            username=username,
            password=password,
            email="admin@example.com",
            role=admin_role
        )
    print(f"Superuser '{username}' is ready with password '{password}' and role '{user.role.role_name}'.")

if __name__ == "__main__":
    create_admin()
