import functools

from django.db import migrations


def migrate_tags(apps, schema_editor, provider):
    EnabledTagKeys = apps.get_model("reporting", "EnabledTagKeys")
    ProviderEnabledTagKeys = apps.get_model("reporting", f"{provider}EnabledTagKeys")
    db_alias = schema_editor.connection.alias

    current_records = ProviderEnabledTagKeys.objects.using(db_alias).all()
    new_records = (
        EnabledTagKeys(key=record.key, enabled=record.enabled, provider_type=provider) for record in current_records
    )

    EnabledTagKeys.objects.using(db_alias).bulk_create(new_records, ignore_conflicts=True)


def unmigrate_tags(apps, schema_editor):
    if getattr(unmigrate_tags, "_ran", None):
        return

    EnabledTagKeys = apps.get_model("reporting", "EnabledTagKeys")
    db_alias = schema_editor.connection.alias
    EnabledTagKeys.objects.using(db_alias).all().delete()

    unmigrate_tags._ran = True


migrate_tags_aws = functools.partial(migrate_tags, provider="AWS")
migrate_tags_azure = functools.partial(migrate_tags, provider="Azure")
migrate_tags_gcp = functools.partial(migrate_tags, provider="GCP")
migrate_tags_oci = functools.partial(migrate_tags, provider="OCI")
migrate_tags_ocp = functools.partial(migrate_tags, provider="OCP")


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0302_unified_enabledtags"),
    ]

    operations = [
        migrations.RunPython(migrate_tags_aws, unmigrate_tags),
        migrations.RunPython(migrate_tags_azure, unmigrate_tags),
        migrations.RunPython(migrate_tags_gcp, unmigrate_tags),
        migrations.RunPython(migrate_tags_oci, unmigrate_tags),
        migrations.RunPython(migrate_tags_ocp, unmigrate_tags),
    ]
