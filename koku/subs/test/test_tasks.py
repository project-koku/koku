#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import datetime
import uuid
from datetime import timedelta
from unittest.mock import patch

import subs.tasks as tasks
from api.provider.models import Provider
from api.utils import DateHelper
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

    def test_check_subs_source_gate(self):
        """Test that the SUBS task is properly gated by sources"""
        self.assertFalse(tasks.check_subs_source_gate(self.schema))

    @patch("subs.tasks.process_upload_keys_to_subs_message.delay")
    @patch("subs.tasks.enable_subs_processing")
    @patch("subs.tasks.get_start_and_end_from_manifest_id")
    @patch("subs.tasks.SUBSDataExtractor")
    def test_collect_subs_report_data_from_manifest(self, mock_extractor, mock_start_end, mock_enable, mock_task):
        """Test that the extraction task is called when processing a manifest"""
        reports = [
            {
                "schema_name": self.schema,
                "provider_type": self.aws_provider_type,
                "provider_uuid": str(self.aws_provider.uuid),
                "tracing_id": self.tracing_id,
            }
        ]
        mock_enable.return_value = True
        mock_start_end.return_value = (self.yesterday, self.today)
        tasks.collect_subs_report_data_from_manifest(reports)
        mock_extractor.return_value.extract_data_to_s3.assert_called_once_with(self.yesterday, self.today)
        mock_task.assert_called()

    @patch("subs.tasks.process_upload_keys_to_subs_message.delay")
    @patch("subs.tasks.DateAccessor.today")
    @patch("subs.tasks.enable_subs_processing")
    @patch("subs.tasks.get_start_and_end_from_manifest_id")
    @patch("subs.tasks.SUBSDataExtractor")
    def test_collect_subs_report_data_from_manifest_no_dates(
        self, mock_extractor, mock_start_end, mock_enable, mock_date, mock_task
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
        mock_enable.return_value = True
        mock_start_end.return_value = (None, None)
        base_date = datetime.datetime.strptime("2023-07-05", "%Y-%m-%d")
        mock_date.return_value = base_date
        tasks.collect_subs_report_data_from_manifest(reports)
        mock_extractor.return_value.extract_data_to_s3.assert_called_once_with(
            base_date.date() - timedelta(days=2), base_date.date()
        )
        mock_task.assert_called()

    @patch("subs.tasks.process_upload_keys_to_subs_message.delay")
    @patch("subs.tasks.enable_subs_processing")
    @patch("subs.tasks.get_start_and_end_from_manifest_id")
    @patch("subs.tasks.SUBSDataExtractor")
    def test_collect_subs_report_data_from_manifest_unsupported_type(
        self, mock_extractor, mock_start_end, mock_enable, mock_task
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
        tasks.collect_subs_report_data_from_manifest(reports)
        mock_enable.assert_not_called()
        mock_start_end.assert_not_called()
        mock_extractor.assert_not_called()
        mock_task.assert_not_called()

    @patch("subs.tasks.process_upload_keys_to_subs_message.delay")
    @patch("subs.tasks.enable_subs_processing")
    @patch("subs.tasks.get_start_and_end_from_manifest_id")
    @patch("subs.tasks.SUBSDataExtractor")
    def test_collect_subs_report_data_from_manifest_gate_fail(
        self, mock_extractor, mock_start_end, mock_enable, mock_task
    ):
        """Test that processing does not continue if the enable_subs_processing gate fails"""
        reports = [
            {
                "schema_name": self.schema,
                "provider_type": self.aws_provider_type,
                "provider_uuid": str(self.aws_provider.uuid),
                "tracing_id": self.tracing_id,
            }
        ]
        mock_enable.return_value = False
        tasks.collect_subs_report_data_from_manifest(reports)
        mock_enable.assert_called_once_with(self.schema)
        mock_start_end.assert_not_called()
        mock_extractor.assert_not_called()
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
