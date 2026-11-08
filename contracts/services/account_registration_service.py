from contracts.repositories import account_registration_repository as workflow_repository
'Account registration policy and persistence, independent of session handling.'
import os

def register_account(method, form, authorization_headers):
    error = None
    if method == 'POST':
        username = form.get('username')
        email = form.get('email')
        password = form.get('password')
        company_id = form.get('company_id')
        role_id = form.get('role_id')
        if not username or not email or (not password) or (not company_id) or (not role_id):
            error = 'Vui lòng điền đầy đủ các trường thông tin.'
        elif workflow_repository.exists_user_for_register_account(username):
            error = 'Tên đăng nhập đã tồn tại.'
        elif workflow_repository.email_already_registered(email):
            error = 'Email đã được sử dụng.'
        else:
            try:
                company = workflow_repository.get_company_for_register_account(company_id)
                role = workflow_repository.get_role_for_register_account(role_id)
                user = workflow_repository.create_user_user_for_register_account(company, email, password, role, username)
                # The blockchain service issues the user's certificate (see identity_service.register_user).
                from contracts.services.ledger_book_service import register_user as issue_certificate, LedgerBookError
                try:
                    issue_certificate(user, company, role)
                    user.status = 'ACTIVE'
                except LedgerBookError as e:
                    print(f'Warning: certificate not issued: {str(e)}')
                    user.status = 'ERROR'
                workflow_repository.save_record_for_register_account(user)
                return (user, None)
            except Exception as e:
                error = f'Lỗi đăng ký: {str(e)}'
    return (None, error)

def ensure_manager_role():
    return workflow_repository.get_or_create_role_for_ensure_manager_role()

def registration_context(error=None):
    return dict(companies=workflow_repository.order_by_company_for_registration_context(), roles=workflow_repository.order_by_role_for_registration_context(), error=error)
