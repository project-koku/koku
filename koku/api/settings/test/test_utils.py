#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from unittest.mock import patch

from django_tenants.utils import schema_context

from api.models import Provider
from api.settings.utils import delayed_summarize_current_month
from api.settings.utils import set_cost_type
from api.settings.utils import set_currency
from api.utils import DateHelper
from masu.processor.tasks import UPDATE_SUMMARY_TABLES_QUEUE
from masu.processor.tasks import UPDATE_SUMMARY_TABLES_QUEUE_XL
from masu.processor.tasks import UPDATE_SUMMARY_TABLES_TASK
from masu.test import MasuTestCase
from reporting.user_settings.models import UserSettings
from reporting_common.models import DelayedCeleryTasks


class TestUserSettingCommon(MasuTestCase):
    """Test cases for currency utils."""

    def setUp(self):
        """Set up test suite."""
        super().setUp()
        with schema_context(self.schema):
            UserSettings.objects.all().delete()

    """Tests for cost_type utils."""

    def test_set_currency_negative(self):
        """Test cost_type raises exception when providing a non-supported cost_type"""
        with self.assertRaises(ValueError):
            set_currency(self.schema, currency_code="BOGUS")

    """Tests for cost_type utils."""

    def test_set_cost_type_negative(self):
        """Test cost_type raises exception when providing a non-supported cost_type"""
        with self.assertRaises(ValueError):
            set_cost_type(self.schema, cost_type_code="BOGUS")

    @patch("api.settings.utils.is_customer_large")
    def test_delayed_summarize_current_month(self, mock_large_customer):
        mock_large_customer.return_value = False
        test_matrix = {
            Provider.PROVIDER_AWS: self.aws_provider,
            Provider.PROVIDER_AZURE: self.azure_provider,
            Provider.PROVIDER_GCP: self.gcp_provider,
            Provider.PROVIDER_OCI: self.oci_provider,
            Provider.PROVIDER_OCP: self.ocp_provider,
        }
        count = 0
        for test_provider_type, test_provider in test_matrix.items():
            with self.subTest(test_provider_type=test_provider_type, test_provider=test_provider):
                with schema_context(self.schema):
                    delayed_summarize_current_month(self.schema_name, [test_provider.uuid], test_provider_type)
                    count += 1
                    self.assertEqual(DelayedCeleryTasks.objects.all().count(), count)
                    db_entry = DelayedCeleryTasks.objects.get(provider_uuid=test_provider.uuid)
                    self.assertEqual(db_entry.task_name, UPDATE_SUMMARY_TABLES_TASK)
                    self.assertTrue(
                        db_entry.get_task_kwargs(),
                        {
                            "provider_type": test_provider_type,
                            "provider_uuid": str(test_provider.uuid),
                            "start_date": str(DateHelper().this_month_start),
                        },
                    )

                    self.assertEqual(db_entry.get_task_args(), [self.schema_name])
                    self.assertEqual(db_entry.queue_name, UPDATE_SUMMARY_TABLES_QUEUE)

    @patch("api.settings.utils.is_customer_large")
    def test_large_customer(self, mock_large_customer):
        mock_large_customer.return_value = True
        delayed_summarize_current_month(self.schema_name, [self.aws_provider.uuid], Provider.PROVIDER_AWS)
        with schema_context(self.schema):
            db_entry = DelayedCeleryTasks.objects.get(provider_uuid=self.aws_provider.uuid)
            self.assertEqual(db_entry.queue_name, UPDATE_SUMMARY_TABLES_QUEUE_XL)
