#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test that django tables are partitioned correctly."""
from django.apps import apps
from django.db import connections
from django.db import DEFAULT_DB_ALIAS

from masu.test import MasuTestCase


def is_model_partitioned(instance):
    """Queries postgres to see if the table is partitioned."""
    connection = connections[DEFAULT_DB_ALIAS]
    table_name = instance._meta.db_table
    check_partition_query = """
    SELECT nmsp_parent.nspname AS parent_schema
    FROM pg_inherits
    JOIN pg_class parent
        ON pg_inherits.inhparent = parent.oid
        JOIN pg_class child
        ON pg_inherits.inhrelid = child.oid
        JOIN pg_namespace nmsp_parent
        ON nmsp_parent.oid = parent.relnamespace
        JOIN pg_namespace nmsp_child
        ON nmsp_child.oid = child.relnamespace
        WHERE parent.relname= %s
        """
    with connection.cursor() as cursor:
        cursor.execute(check_partition_query, [table_name])
        return bool(cursor.fetchone())


class TestPartitionCheck(MasuTestCase):
    """This test suite checks that the models we partitioned
    paritioned in django are actually partitioned in postgresql.
    """

    def test_postgres_tables_are_partitioned(self):
        """
        To actually partition models you need to use the
        set_pg_extended_mode funciton in the migration.
        This requirement can be easily missed in our
        workflow.

        If this test is failing, that means a migration
        failed to use this requirement and would not
        actually create a partitioned table.

        Example:
        - https://github.com/project-koku/koku/pull/4737"""
        # Collect models from django
        partitioned_models = []
        for model in apps.get_models():
            if hasattr(model, "PartitionInfo"):
                partitioned_models.append(model)

        if not partitioned_models:
            return

        # Check if models are actually partitioned in PostgreSQL
        for model in partitioned_models:
            with self.subTest(model=model):
                msg = (
                    "Model {model.__name__} is not partitioned.\n"
                    "\nAre `set_pg_extended_mode` and `unset_pg_extended_mode`"
                    " used in the model's migration?"
                )
                self.assertTrue(is_model_partitioned(model), msg)
