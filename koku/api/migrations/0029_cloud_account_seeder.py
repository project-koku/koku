

from django.db import migrations

def seed_cost_management_aws_account_id(apps, schema_editor):
    """Create a cloud account, using the historical CloudAccount model."""
    CloudAccount = apps.get_model('api', 'CloudAccount')
    cloud_account = CloudAccount.objects.create(
            name='AWS', value='589173575009', description="Cost Management's AWS account ID")
    cloud_account.save()

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0028_cloud_account'),
    ]

    operations = [
        migrations.RunPython(seed_cost_management_aws_account_id),
    ]
