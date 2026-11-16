"""A2 domain rules used by the main Contract Guard web application."""



def can_review(user):
    from contract.core.services.access_service import is_manager
    return is_manager(user)


