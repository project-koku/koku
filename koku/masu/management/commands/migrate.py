# Originally from django-tenant-schemas, modified to use our own MigrateSchemas command.
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from tenant_schemas.utils import django_is_in_test_mode

from .migrate_schemas import Command as MigrateSchemasCommand


class Command(BaseCommand):
    def handle(self, *args, **options):
        database = options.get("database", "default")
        if settings.DATABASES[database]["ENGINE"] == "tenant_schemas.postgresql_backend":
            raise CommandError(
                "migrate has been disabled, for database '{}'. Use migrate_schemas "
                "instead. Please read the documentation if you don't know why you "
                "shouldn't call migrate directly!".format(database)
            )
        super().handle(*args, **options)


if django_is_in_test_mode():
    Command = MigrateSchemasCommand  # noqa: F811
