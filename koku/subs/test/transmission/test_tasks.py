#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the SUBS task."""
import datetime
import uuid
from unittest.mock import patch

from subs.test import SUBSTestCase
from subs.transmission.tasks import collect_subs_transmission_report_data


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

    @patch("subs.transmission.tasks.enable_subs_processing")
    def test_collect_subs_transmission_report_data_processing_enabled(self, mock_enable_subs_process):
        """Test collect_subs_report_data function with subs processing enabled."""

        mock_enable_subs_process.return_value = True
        with self.assertLogs("subs.transmission.tasks", "INFO") as _logs:
            collect_subs_transmission_report_data(
                self.schema_name,
                self.aws_provider_type,
                self.aws_provider_uuid,
                self.start_date,
                self.end_date,
                self.tracing_id,
            )

            self.assertIn("collecting subs report data", _logs.output[0])

    @patch("subs.transmission.tasks.enable_subs_processing")
    def test_collect_subs_report_data_processing_disabled(self, mock_enable_subs_process):
        """Test collect_subs_report_data function with subs processing disabled."""

        mock_enable_subs_process.return_value = False

        with self.assertLogs("subs.transmission.tasks", "INFO") as _logs:
            collect_subs_transmission_report_data(
                self.schema_name,
                self.aws_provider_type,
                self.aws_provider_uuid,
                self.start_date,
                self.end_date,
                self.tracing_id,
            )

            self.assertIn("skipping subs report generation for transmission", _logs.output[0])
