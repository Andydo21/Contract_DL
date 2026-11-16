"""Session and user lookups of the shared JWT middleware, read from the contract web database (used by the services
that do not have the contracts app)."""


def _cursor():
    from django.db import connections
    return connections['contract_db' if 'contract_db' in connections else 'default'].cursor()


def session_data(session_key):
    """The encoded session data of a Django session, or None."""
    with _cursor() as cursor:
        cursor.execute("SELECT session_data FROM django_session WHERE session_key = %s", [session_key])
        row = cursor.fetchone()
    return row[0] if row else None


def session_user(user_id):
    """(id, username, role_name, company_id, is_superuser) of a contract-web user, or None."""
    with _cursor() as cursor:
        cursor.execute("""
            SELECT u.id, u.username, r.role_name, u.company_id, u.is_superuser
            FROM contracts_user u
            LEFT JOIN contracts_role r ON u.role_id = r.id
            WHERE u.id = %s
        """, [int(user_id)])
        return cursor.fetchone()
