from contract.contracts.models import Contract, Review, AuditLog


class AuditLogRepository:
    @staticmethod
    def log_action(user, action, target_model, target_id):
        contract = None
        if target_model == "Contract":
            try:
                contract = Contract.all_objects.get(id=target_id)
            except Contract.DoesNotExist:
                pass
        elif target_model == "Review":
            try:
                review = Review.objects.get(id=target_id)
                contract = review.analysis.version.contract
            except Exception:
                pass
        
        return AuditLog.objects.create(
            user=user,
            contract=contract,
            action=action
        )


    @staticmethod
    def contract_by_id(contract_id):
        return Contract.objects.get(id=contract_id)

    @staticmethod
    def record_request(**fields):
        return AuditLog.objects.create(**fields)
