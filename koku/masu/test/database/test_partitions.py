#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test that expected tables are partitioned correctly."""
from unittest.mock import Mock
from unittest.mock import patch

from masu.management.commands.create_partition_check import Command
from masu.management.commands.create_partition_check import get_django_partitioned_models
from masu.management.commands.create_partition_check import is_model_partitioned
from masu.test import MasuTestCase
from reporting.provider.ocp.models import OCPPodSummaryByNodeP
from reporting.provider.ocp.models import OpenshiftCostCategory


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
        partitioned_models = get_django_partitioned_models()
        if not partitioned_models:
            return

        # Check if models are actually partitioned in PostgreSQL
        for model in partitioned_models:
            with self.subTest(model=model):
                self.assertTrue(is_model_partitioned(model))


class TestPartitionCheckCommand(MasuTestCase):
    def setUp(self):
        self.command = Command()
        self.stdout = Mock()
        self.command.stdout = self.stdout
        self.partitioned_model = OCPPodSummaryByNodeP
        self.unpartitioned_model = OpenshiftCostCategory

    def test_get_django_partitioned_models(self):
        # Ensure that the method correctly identifies partitioned models
        partitioned_models = get_django_partitioned_models()
        self.assertIn(self.partitioned_model, partitioned_models)

    def test_is_model_partitioned(self):
        # Mock database operations to simulate partitioned and non-partitioned models

        # Test with a partitioned model
        is_partitioned = is_model_partitioned(self.partitioned_model)
        self.assertTrue(is_partitioned)

        # Test with a non-partitioned model
        is_partitioned = is_model_partitioned(self.unpartitioned_model)
        self.assertFalse(is_partitioned)

    @patch("masu.management.commands.create_partition_check.get_django_partitioned_models")
    @patch("masu.management.commands.create_partition_check.is_model_partitioned")
    def test_handle(self, mock_is_model_partitioned, mock_get_django_partitioned_models):
        # Mock get_django_partitioned_models to return a list with YourPartitionedModel
        mock_get_django_partitioned_models.return_value = []

        # Mock is_model_partitioned to return True for the partitioned model
        mock_is_model_partitioned.return_value = True

        # Call the handle method
        self.command.handle()

        # Ensure that the expected output is in stdout
        self.stdout.write.assert_called_with(self.command.style.SUCCESS("No models with PartitionInfo found."))

        mock_get_django_partitioned_models.return_value = [self.unpartitioned_model]
        # Reset the mock to simulate a non-partitioned model
        mock_is_model_partitioned.return_value = False
        self.stdout.reset_mock()

        # Call the handle method again
        self.command.handle()

        # Ensure that the error message is printed for the non-partitioned model
        self.stdout.write.assert_called_with(
            self.command.style.ERROR(f"Model {self.unpartitioned_model.__name__} is not partitioned.")
        )
