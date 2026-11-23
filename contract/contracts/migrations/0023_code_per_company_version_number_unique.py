from django.db import migrations, models


def renumber_duplicate_versions(apps, schema_editor):
    """Versions created by two uploads at once may share a number; give each contract's versions 1..n again, in the
    order they were created, so the unique constraint below can be added."""
    ContractVersion = apps.get_model('contracts', 'ContractVersion')
    duplicated = (ContractVersion.objects.values('contract_id', 'version_number')
                  .annotate(n=models.Count('id')).filter(n__gt=1).values_list('contract_id', flat=True).distinct())
    for contract_id in set(duplicated):
        versions = list(ContractVersion.objects.filter(contract_id=contract_id).order_by('version_number', 'created_at', 'id'))
        # Move out of the way first, so no intermediate state collides with itself.
        for offset, version in enumerate(versions, start=1):
            ContractVersion.objects.filter(pk=version.pk).update(version_number=-offset)
        for number, version in enumerate(versions, start=1):
            ContractVersion.objects.filter(pk=version.pk).update(version_number=number)


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0022_contract_code_unique_when_not_deleted'),
    ]

    operations = [
        migrations.RemoveConstraint(model_name='contract', name='contract_code_unique_when_not_deleted'),
        migrations.AddConstraint(
            model_name='contract',
            constraint=models.UniqueConstraint(condition=models.Q(('company__isnull', False), ('deleted_at__isnull', True)),
                                               fields=('company', 'contract_code'), name='contract_code_unique_per_company'),
        ),
        migrations.AddConstraint(
            model_name='contract',
            constraint=models.UniqueConstraint(condition=models.Q(('company__isnull', True), ('deleted_at__isnull', True)),
                                               fields=('contract_code',), name='contract_code_unique_without_company'),
        ),
        migrations.RunPython(renumber_duplicate_versions, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='contractversion',
            constraint=models.UniqueConstraint(fields=('contract', 'version_number'), name='contract_version_number_unique'),
        ),
    ]
