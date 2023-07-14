#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from datetime import timedelta
from unittest.mock import patch

import subs.tasks as tasks
from subs.test import SUBSTestCase


class TestSUBSTasks(SUBSTestCase):
    """Test cases for SUBS Celery tasks."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()

    def setUp(self):
        """Set up the class."""
        super().setUp()
        self.yesterday = self.dh.today.date() - timedelta(days=1)
        self.start_date = self.dh.today.date() - timedelta(days=2)
        self.end_date = self.dh.today.date()
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

    @patch("subs.tasks.enable_subs_processing")
    @patch("subs.tasks.get_start_and_end_from_manifest_id")
    def test_collect_subs_report_data_from_manifest(self, mock_start_end, mock_enable):
        """Test that the extraction task is called when processing a manifest"""

        mock_enable.return_value = True
        mock_start_end.return_value = (self.start_date, self.end_date)
        with self.assertLogs("subs.tasks", "INFO") as _logs:
            tasks.collect_subs_report_data_from_manifest(self.reports_to_subs_summarize)

            self.assertIn("collecting subs report data", _logs.output[0])

    def test_process_upload_keys_to_subs_message(self):
        """Test that the subs processing tasks makes the appropriate class and function call"""
        upload_keys = ["fake_key"]
        context = {"some_context": "here"}

        with self.assertLogs("subs.tasks", "INFO") as _logs:
            tasks.process_upload_keys_to_subs_message(
                context,
                self.schema_name,
                self.tracing_id,
                upload_keys,
            )

            self.assertIn("processing subs data to kafka", _logs.output[0])
