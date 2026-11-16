from django.db import migrations, models
import django.db.models.deletion


def remove_unlinked(apps, schema_editor):
    apps.get_model('ai_extract', 'LegalDocument').objects.filter(contract__isnull=True).delete()


class Migration(migrations.Migration):
    # Deleting linked provisions leaves deferred triggers that block the ALTER in one transaction.
    atomic = False

    dependencies = [
        ('ai_extract', '0008_legal_document_contract'),
    ]

    operations = [
        migrations.RunPython(remove_unlinked, migrations.RunPython.noop),
        migrations.DeleteModel(name='LegalProvision'),
        migrations.AddField(model_name='legaldocument', name='public', field=models.BooleanField(default=False)),
        migrations.AlterField(model_name='legaldocument', name='contract', field=models.OneToOneField(
            on_delete=django.db.models.deletion.CASCADE, related_name='legal_document', to='contracts.contract')),
    ]
