import os
import django
import sys

sys.path.append('d:\\Django_project\\RiskDL')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from contracts.models import User

admin_user = User.objects.filter(username='admin').first()
if admin_user:
    admin_user.set_password('password123')
    admin_user.save()
    print("Admin password reset successfully to 'password123'!")
else:
    print("Admin user not found!")
