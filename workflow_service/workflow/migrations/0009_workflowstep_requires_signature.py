import re
from django.db import migrations, models


def mark_signing_steps(apps, schema_editor):
    Step = apps.get_model('workflow', 'WorkflowStep')
    for step in Step.objects.all().iterator():
        if re.search(r'ký kết|chữ ký|\bsign(?:ing)?\b', step.step_name, re.I):
            Step.objects.filter(pk=step.pk).update(requires_signature=True)


class Migration(migrations.Migration):
    dependencies = [('workflow', '0008_stepdependency')]
    operations = [migrations.AddField(model_name='workflowstep', name='requires_signature', field=models.BooleanField(default=False)),
                  migrations.RunPython(mark_signing_steps, migrations.RunPython.noop)]
