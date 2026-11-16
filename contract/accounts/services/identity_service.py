from contract.accounts.repositories import identity_data_repository as data_repository
from contract.core.services.results import ServiceResult

def register_company(method, data, authorization_headers):
    """POST: Register a new Company in DB and anchor it to the blockchain."""
    if method != 'POST':
        return ServiceResult({'error': 'Method not allowed.'}, status=405)
    try:
        name = data.get('company_name')
        tax_code = data.get('tax_code')
        if not name or not tax_code:
            return ServiceResult({'error': 'Thiếu tên công ty hoặc mã số thuế'}, status=400)
        existing_comp = data_repository.find_company_by_tax_code(tax_code) or data_repository.find_company_by_name(name)
        if existing_comp:
            return ServiceResult({'error': f'Công ty "{existing_comp.company_name}" (MST: {existing_comp.tax_code}) đã tồn tại trong hệ thống.'}, status=400)
        company = data_repository.create_company_for_register_company(name, tax_code)
        # Identity lives in the database: the chaincode only accepts version-bound contract operations (an anchor or a
        # signature), and a signer's key is bound on the ledger with the first signature (see ledger_service).
        company.status = 'ACTIVE'
        data_repository.save_company_for_register_company(company)
        return ServiceResult({'status': 'success', 'company_id': company.id, 'company_name': company.company_name, 'tax_code': company.tax_code, 'tx_hash': company.tx_hash, 'block_number': company.block_number, 'block_hash': company.block_hash})
    except Exception as e:
        return ServiceResult({'error': str(e)}, status=500)

def register_user(user, method, data, authorization_headers):
    """POST: Register a new User in DB and anchor them to the blockchain."""
    if method != 'POST':
        return ServiceResult({'error': 'Method not allowed.'}, status=405)
    try:
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        company_id = data.get('company_id')
        role_id = data.get('role_id')
        if not username or not email or (not password) or (not company_id) or (not role_id):
            return ServiceResult({'error': 'Thiếu thông tin đăng ký nhân sự'}, status=400)
        from contract.contracts.models import Company, Role
        try:
            company = data_repository.get_company_for_register_user(company_id)
            role = data_repository.get_role_for_register_user(role_id)
        except (Company.DoesNotExist, Role.DoesNotExist):
            return ServiceResult({'error': 'Công ty hoặc Vai trò không tồn tại'}, status=404)
        # Only a system superuser registers staff for another company; a manager registers staff of their own company.
        # user=None is a trusted internal caller (seed scripts).
        if user is not None and not user.is_superuser and company.pk != user.company_id:
            return ServiceResult({'error': 'Chỉ được đăng ký nhân sự cho doanh nghiệp của mình.'}, status=403)
        existing_user = data_repository.first_user_for_register_user(username)
        if existing_user:
            if existing_user.status == 'ACTIVE' and existing_user.block_number:
                return ServiceResult({'error': f'Tài khoản "{username}" đã tồn tại và đã được Anchor trên Blockchain.'}, status=400)
            if user is not None and not user.is_superuser and existing_user.company_id != user.company_id:
                return ServiceResult({'error': f'Tài khoản "{username}" đã tồn tại.'}, status=400)
            user = existing_user
            user.email = email
            user.set_password(password)
            user.company = company
            user.role = role
            user.status = 'ACTIVE'
            data_repository.save_user_for_register_user(user)
        else:
            user = data_repository.create_registered_user(username, email, password, company, role)
        # The blockchain service issues the user's certificate; the user's signing key is bound to it on Fabric by the
        # first signature (the chaincode takes version-bound operations, not unsigned account writes).
        from blockchain.ledger.services.ledger_book_service import register_user as issue_certificate, LedgerBookError
        try:
            certificate = issue_certificate(user, company, role)
        except LedgerBookError as e:
            user.status = 'ERROR'
            data_repository.save_user_for_register_user(user)
            return ServiceResult({'error': f'Chưa cấp được chứng thư blockchain: {str(e)}'}, status=502)
        user.status = 'ACTIVE'
        data_repository.save_user_for_register_user(user)
        return ServiceResult({'status': 'success', 'user_id': user.id, 'username': user.username, 'email': user.email, 'company_name': company.company_name, 'role_name': role.role_name, 'certificate_serial': certificate.get('serial_number'), 'certificate_status': certificate.get('certificate_status')})
    except Exception as e:
        return ServiceResult({'error': str(e)}, status=500)

def companies_list(data, user=None):
    """GET: Get list of all companies (a non-superuser sees only their own company)."""
    companies = data_repository.order_by_company_for_companies_list()
    if user is not None and not user.is_superuser:
        companies = [c for c in companies if c.pk == user.company_id]
    seen = set()
    data = []
    for c in companies:
        key = (c.tax_code or c.company_name).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        data.append({'id': c.id, 'company_name': c.company_name, 'tax_code': c.tax_code, 'status': c.status, 'tx_hash': c.tx_hash, 'block_number': c.block_number, 'block_hash': c.block_hash})
    return ServiceResult(data)

def users_list(data, user=None):
    """GET: Get list of all users (a non-superuser sees only the users of their own company)."""
    users = data_repository.order_by_user_for_users_list()
    if user is not None and not user.is_superuser:
        users = [u for u in users if u.company_id == user.company_id]
    data = []
    for u in users:
        data.append({'id': u.id, 'username': u.username, 'email': u.email, 'company_name': u.company.company_name if u.company else 'N/A', 'role_name': u.role.role_name if u.role else 'N/A', 'status': u.status, 'tx_hash': u.tx_hash, 'block_number': u.block_number, 'block_hash': u.block_hash})
    return ServiceResult(data)

def roles_list(data):
    """GET: Get list of all roles."""
    data_repository.get_or_create_role_for_roles_list()
    roles = data_repository.order_by_role_for_roles_list()
    data = [{'id': r.id, 'role_name': r.role_name} for r in roles]
    return ServiceResult(data)
