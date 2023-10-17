from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connections
from django.db import DEFAULT_DB_ALIAS


def get_django_partitioned_models():
    """Collects models with PartitionInfo set."""
    partitioned_models = []
    for model in apps.get_models():
        if hasattr(model, "PartitionInfo"):
            partitioned_models.append(model)
    return partitioned_models


def is_model_partitioned(instance):
    """Queries postgres to see if the table is partitioned."""
    connection = connections[DEFAULT_DB_ALIAS]
    table_name = instance._meta.db_table
    check_partition_query = "SELECT nmsp_parent.nspname AS parent_schema FROM pg_inherits JOIN pg_class parent ON pg_inherits.inhparent = parent.oid JOIN pg_class child ON pg_inherits.inhrelid = child.oid JOIN pg_namespace nmsp_parent ON nmsp_parent.oid = parent.relnamespace JOIN pg_namespace nmsp_child ON nmsp_child.oid = child.relnamespace WHERE parent.relname= %s"  # noqa: E501
    with connection.cursor() as cursor:
        cursor.execute(check_partition_query, [table_name])
        return bool(cursor.fetchone())


class Command(BaseCommand):
    help = "Check if models with PartitionInfo are actually partitioned in PostgreSQL."

    def handle(self, *args, **options):
        # Collect all models that use PartitionInfo
        partitioned_models = get_django_partitioned_models()
        if not partitioned_models:
            self.stdout.write(self.style.SUCCESS("No models with PartitionInfo found."))
            return

        # Check if models are actually partitioned in PostgreSQL
        for model in partitioned_models:
            if not is_model_partitioned(model):
                self.stdout.write(self.style.ERROR(f"Model {model.__name__} is not partitioned."))
