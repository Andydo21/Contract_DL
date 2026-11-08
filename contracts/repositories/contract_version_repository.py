from contracts.models import ContractVersion


class ContractVersionRepository:
    @staticmethod
    def get_version_by_id(version_id):
        try:
            return ContractVersion.objects.select_related('contract').get(id=version_id)
        except ContractVersion.DoesNotExist:
            return None

    @staticmethod
    def get_versions_by_ids(version_ids):
        return ContractVersion.objects.filter(id__in=version_ids).select_related('contract')
