#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import uuid
from datetime import timedelta
from unittest.mock import patch

import subs.tasks as tasks
from api.provider.models import Provider
from api.utils import DateHelper
from reporting_common.models import CostUsageReportManifest
from subs.test import SUBSTestCase


class TestSUBSTasks(SUBSTestCase):
    """Test cases for SUBS Celery tasks."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.dh = DateHelper()
        cls.tracing_id = str(uuid.uuid4())
        cls.dh = DateHelper()
        cls.today = cls.dh.today
        cls.yesterday = cls.today - timedelta(days=1)
        cls.metered_on = "rhel"
        cls.metered_off = ""

    @patch("subs.tasks.process_upload_keys_to_subs_message.delay")
    @patch("subs.tasks.enable_subs_messaging")
    @patch("subs.tasks.enable_subs_extraction")
    @patch("subs.tasks.get_month_start_from_report")
    @patch("subs.tasks.SUBSDataExtractor")
    def test_extract_subs_data_from_reports(
        self, mock_extractor, mock_month_start, mock_extract_enable, mock_message_enable, mock_task
    ):
        """Test that the extraction task is called when processing a manifest"""
        reports = [
            {
                "schema_name": self.schema,
                "provider_type": self.aws_provider_type,
                "provider_uuid": str(self.aws_provider.uuid),
                "tracing_id": self.tracing_id,
            }
        ]
        mock_extract_enable.return_value = True
        mock_message_enable.return_value = True
        expected_month_start = self.dh.month_start(self.yesterday)
        mock_month_start.return_value = expected_month_start
        tasks.extract_subs_data_from_reports(reports, self.metered_on)
        mock_extractor.return_value.extract_data_to_s3.assert_called_once_with(expected_month_start)
        mock_task.assert_called()

    @patch("subs.tasks.process_upload_keys_to_subs_message.delay")
    @patch("subs.tasks.enable_subs_messaging")
    @patch("subs.tasks.enable_subs_extraction")
    @patch("subs.tasks.SUBSDataExtractor")
    def test_extract_subs_data_from_reports_with_start(
        self, mock_extractor, mock_extract_enable, mock_message_enable, mock_task
    ):
        """Test that the extraction task is called when processing a manifest"""
        reports = [
            {
                "schema_name": self.schema,
                "provider_type": self.aws_provider_type,
                "provider_uuid": str(self.aws_provider.uuid),
                "tracing_id": self.tracing_id,
                "start": self.yesterday.strftime("%Y-%m-%d"),
            }
        ]
        mock_extract_enable.return_value = True
        mock_message_enable.return_value = True
        expected_month_start = self.dh.month_start_utc(self.yesterday)
        tasks.extract_subs_data_from_reports(reports, "rhel")
        mock_extractor.return_value.extract_data_to_s3.assert_called_once_with(expected_month_start)
        mock_task.assert_called()

    @patch("subs.tasks.process_upload_keys_to_subs_message.delay")
    @patch("subs.tasks.enable_subs_messaging")
    @patch("subs.tasks.enable_subs_extraction")
    @patch("subs.tasks.get_month_start_from_report")
    @patch("subs.tasks.SUBSDataExtractor")
    def test_extract_subs_data_from_reports_no_manifest(
        self, mock_extractor, mock_month_start, mock_extract_enable, mock_message_enable, mock_task
    ):
        """Test that the dates used for extraction are properly set if there aren't dates from a manifest"""
        reports = [
            {
                "schema_name": self.schema,
                "provider_type": self.aws_provider_type,
                "provider_uuid": str(self.aws_provider.uuid),
                "tracing_id": self.tracing_id,
            }
        ]
        mock_extract_enable.return_value = True
        mock_message_enable.return_value = True
        mock_month_start.return_value = None
        tasks.extract_subs_data_from_reports(reports, self.metered_on)
        mock_extractor.return_value.extract_data_to_s3.assert_not_called()
        mock_task.assert_not_called()

    @patch("subs.tasks.process_upload_keys_to_subs_message.delay")
    @patch("subs.tasks.enable_subs_messaging")
    @patch("subs.tasks.enable_subs_extraction")
    @patch("subs.tasks.get_month_start_from_report")
    @patch("subs.tasks.SUBSDataExtractor")
    def test_extract_subs_data_from_reports_unsupported_type(
        self, mock_extractor, mock_month_start, mock_extract_enable, mock_message_enable, mock_task
    ):
        """Test that processing does not continue if a provider type is unsupported"""
        reports = [
            {
                "schema_name": self.schema,
                "provider_type": Provider.PROVIDER_OCP,
                "provider_uuid": str(self.aws_provider.uuid),
                "tracing_id": self.tracing_id,
            }
        ]
        tasks.extract_subs_data_from_reports(reports, self.metered_on)
        mock_extract_enable.assert_not_called()
        mock_message_enable.assert_not_called()
        mock_month_start.assert_not_called()
        mock_extractor.assert_not_called()
        mock_task.assert_not_called()

    @patch("subs.tasks.process_upload_keys_to_subs_message.delay")
    @patch("subs.tasks.enable_subs_messaging")
    @patch("subs.tasks.enable_subs_extraction")
    @patch("subs.tasks.get_month_start_from_report")
    @patch("subs.tasks.SUBSDataExtractor")
    def test_extract_subs_data_from_reports_extract_gate_fail(
        self, mock_extractor, mock_month_start, mock_extract_enable, mock_message_enable, mock_task
    ):
        """Test that processing does not continue if the enable_subs_extraction gate fails"""
        reports = [
            {
                "schema_name": self.schema,
                "provider_type": self.aws_provider_type,
                "provider_uuid": str(self.aws_provider.uuid),
                "tracing_id": self.tracing_id,
            }
        ]
        mock_extract_enable.return_value = False
        mock_message_enable.return_value = True
        tasks.extract_subs_data_from_reports(reports, self.metered_off)
        mock_extract_enable.assert_called_once_with(self.schema, self.metered_off)
        mock_month_start.assert_not_called()
        mock_extractor.assert_not_called()
        mock_message_enable.assert_not_called()
        mock_task.assert_not_called()

    @patch("subs.tasks.process_upload_keys_to_subs_message.delay")
    @patch("subs.tasks.enable_subs_messaging")
    @patch("subs.tasks.enable_subs_extraction")
    @patch("subs.tasks.get_month_start_from_report")
    @patch("subs.tasks.SUBSDataExtractor")
    def test_extract_subs_data_from_reports_message_gate_fail(
        self, mock_extractor, mock_month_start, mock_extract_enable, mock_message_enable, mock_task
    ):
        """Test that extraction occurs but messaging does not if the enable_subs_messaging gate fails"""
        reports = [
            {
                "schema_name": self.schema,
                "provider_type": self.aws_provider_type,
                "provider_uuid": str(self.aws_provider.uuid),
                "tracing_id": self.tracing_id,
            }
        ]
        mock_extract_enable.return_value = True
        mock_message_enable.return_value = False
        expected_month_start = self.dh.month_start(self.yesterday)
        mock_month_start.return_value = expected_month_start
        tasks.extract_subs_data_from_reports(reports, self.metered_on)
        mock_extract_enable.assert_called_once_with(self.schema, self.metered_on)
        mock_month_start.assert_called()
        mock_extractor.assert_called()
        mock_message_enable.assert_called_once_with(self.schema)
        mock_task.assert_not_called()

    @patch("subs.tasks.SUBSDataMessenger")
    def test_process_upload_keys_to_subs_message(self, mock_messenger):
        """Test that the subs processing tasks makes the appropriate class and function call"""
        upload_keys = ["fake_key"]
        context = {"some_context": "here"}
        schema_name = self.schema
        tracing_id = "trace_me"
        tasks.process_upload_keys_to_subs_message(context, schema_name, tracing_id, upload_keys)
        mock_messenger.assert_called_once_with(context, schema_name, tracing_id)
        mock_messenger.return_value.process_and_send_subs_message.assert_called_once_with(upload_keys)

    def test_get_month_start_from_report_with_start(self):
        """Test the returned start date from get_month_start when a start is included for the report"""
        report = {
            "schema_name": self.schema,
            "provider_type": self.aws_provider_type,
            "provider_uuid": str(self.aws_provider.uuid),
            "tracing_id": self.tracing_id,
            "start": self.yesterday.strftime("%Y-%m-%d"),
        }
        actual = tasks.get_month_start_from_report(report)
        expected = self.dh.month_start_utc(self.yesterday)
        self.assertEqual(expected, actual)

    def test_get_month_start_from_report_from_manifest(self):
        """Test the returned start date from get_month_start with a manifest id"""
        report = {
            "schema_name": self.schema,
            "provider_type": self.aws_provider_type,
            "provider_uuid": str(self.aws_provider.uuid),
            "tracing_id": self.tracing_id,
        }
        manifest = CostUsageReportManifest.objects.filter(provider_id=self.aws_provider.uuid).first()
        report["manifest_id"] = manifest.id
        actual = tasks.get_month_start_from_report(report)
        expected = manifest.billing_period_start_datetime
        self.assertEqual(expected, actual)

    def test_get_month_start_from_report_no_manifest(self):
        """Test the returned start date from get_month_start when no manifest is found"""
        report = {
            "schema_name": self.schema,
            "provider_type": self.aws_provider_type,
            "provider_uuid": str(self.aws_provider.uuid),
            "tracing_id": self.tracing_id,
        }
        report["manifest_id"] = -1
        actual = tasks.get_month_start_from_report(report)
        self.assertIsNone(actual)

    def test_enable_subs_extraction(self):
        """Test that different values for metered result in correct returns."""
        test_table = {self.metered_on: True, self.metered_off: False, "rhel_is_the_best": False}
        for meter_value, expected in test_table.items():
            with self.subTest(meter_value=meter_value):
                self.assertEqual(tasks.enable_subs_extraction(self.schema, meter_value), expected)
