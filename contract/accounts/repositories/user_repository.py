

class UserRepository:
    @staticmethod
    def get_by_id(user_id):
        """The user; raises User.DoesNotExist."""
        from django.contrib.auth import get_user_model
        return get_user_model().objects.get(id=user_id)

    @staticmethod
    def demo_user():
        """Prefer the superuser 'admin' so all contracts are visible in visible_contracts()."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        return (User.objects.filter(username='admin', is_superuser=True).first()
                or User.objects.filter(is_superuser=True).first()
                or User.objects.filter(role__role_name='ADMIN').first()
                or User.objects.first())
