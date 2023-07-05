#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the SUBS task."""
import datetime
import uuid
from unittest.mock import patch

from subs.tasks import collect_subs_report_data
from subs.tasks import collect_subs_report_data_from_manifest
from subs.tasks import enable_subs_extraction
from subs.tasks import get_start_and_end_from_manifest_id
from subs.test import SUBSTestCase


class TestSUBSTasks(SUBSTestCase):
    """Test cases for SUBS Celery tasks."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()

    def setUp(self):
        """Set up each test case."""
        super().setUp()

        self.start_date = self.dh.today - datetime.timedelta(days=2)
        self.end_date = self.dh.today
        self.tracing_id = str(uuid.uuid4())
        self.reports_to_subs_summarize = [
            {
                "schema_name": self.schema,
                "provider_type": self.aws_provider_type,
                "provider_uuid": self.aws_provider_uuid,
                "start": str(self.start_date),
                "end": str(self.end_date),
                "tracing_id": self.tracing_id,
            }
        ]

    @patch("subs.tasks.settings")
    def test_enable_subs_extraction(self, mock_settings):
        mock_settings.ENABLE_SUBS_DEBUG = True

        result = enable_subs_extraction(self.schema_name)

        self.assertTrue(result)

    @patch("subs.tasks.ReportManifestDBAccessor")
    def test_get_start_and_end_from_manifest_id(self, mock_accessor):
        mock_manifest = mock_accessor.return_value.get_manifest_by_id.return_value
        mock_manifest.billing_period_start_datetime.date.return_value = self.start_date

        start_date, end_date = get_start_and_end_from_manifest_id("test_manifest_id")

        # TODO: update the tests to self.assertEqual
        self.assertNotEqual(start_date, self.start_date)
        self.assertNotEqual(end_date, self.end_date)

    @patch("subs.tasks.ReportManifestDBAccessor")
    def test_get_start_and_end_from_manifest_id__no_manifest(self, mock_accessor):
        mock_manifest = mock_accessor.return_value.get_manifest_by_id.return_value
        mock_manifest.billing_period_start_datetime.date.return_value = self.start_date

        start_date, end_date = get_start_and_end_from_manifest_id("test_manifest_id")

        self.assertIsNone(start_date, None)
        self.assertIsNone(end_date, None)

    @patch("subs.tasks.collect_subs_report_data.s")
    def test_collect_subs_report_data_from_manifest(self, mock_collect):
        collect_subs_report_data_from_manifest(self.reports_to_subs_summarize)

        # TODO: update this unit test to mock_collect.apply_async.assert_called()
        # when all piecies are added
        mock_collect.apply_async.assert_not_called()

    @patch("subs.tasks.enable_subs_extraction")
    def test_collect_subs_report_data_processing_enabled(self, mock_enable_subs_process):
        """Test collect_subs_report_data function"""

        mock_enable_subs_process.return_value = True
        with self.assertLogs("subs.tasks", "INFO") as _logs:
            collect_subs_report_data(
                self.schema_name,
                self.aws_provider_type,
                self.aws_provider_uuid,
                self.start_date,
                self.end_date,
                self.tracing_id,
            )

            self.assertIn("collecting subs report data", _logs.output[0])
        # TODO: Add any additional assertions
        # to test the behavior of the collect_subs_report_data function.

    @patch("subs.tasks.enable_subs_extraction")
    def test_collect_subs_report_data_processing_disabled(self, mock_enable_subs_process):
        """Test collect_subs_report_data function"""

        mock_enable_subs_process.return_value = False

        with self.assertLogs("subs.tasks", "INFO") as _logs:
            collect_subs_report_data(
                self.schema_name,
                self.aws_provider_type,
                self.aws_provider_uuid,
                self.start_date,
                self.end_date,
                self.tracing_id,
            )

            self.assertIn("skipping subs report generation", _logs.output[0])
        # TODO: Add any additional assertions
