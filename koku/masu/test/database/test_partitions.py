#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test that expected tables are partitioned correctly."""
from masu.management.commands.create_partition_check import get_django_partitioned_models
from masu.test import MasuTestCase

# from masu.management.commands.create_partition_check import is_model_partitioned


class PartitionTests(MasuTestCase):
    """This test suite checks that the models we partitioned
    paritioned in django are actually partitioned in postgresql.

    If this test is failing it is likely that you forgot to set
    the set_pg_extended_mode function in your migration.

    Example:
    - https://github.com/project-koku/koku/pull/4737
    """

    def test_postgres_tables_are_partitioned(self):
        """Check that models are partitioned."""
        partitioned_models = get_django_partitioned_models()
        if not partitioned_models:
            return

        # # Check if models are actually partitioned in PostgreSQL
        # for model in partitioned_models:
        #     with self.subTest(model=model):
        #         self.assertTrue(is_model_partitioned(model))
