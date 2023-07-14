#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import uuid
from datetime import timedelta
from unittest.mock import patch

import subs.tasks as tasks
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
        cls.today = cls.dh.today
        cls.yesterday = cls.today - timedelta(days=1)

    @patch("subs.tasks.enable_subs_processing")
    @patch("subs.tasks.get_start_and_end_from_manifest_id")
    def test_collect_subs_report_data_from_manifest(self, mock_start_end, mock_enable):
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
        with self.assertLogs("subs.tasks", "INFO") as _logs:
            tasks.collect_subs_report_data_from_manifest(reports)

            self.assertIn("collecting subs report data", _logs.output[0])
