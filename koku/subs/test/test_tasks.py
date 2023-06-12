#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the SUBS task."""
import logging

from subs.tasks import collect_subs_cur_data
from subs.test import SUBSTestCase

LOG = logging.getLogger(__name__)


class TestSUBSTasks(SUBSTestCase):
    """Test cases for SUBS Celery tasks."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()

    def test_collect_subs_cur_data_all_dates(self):
        """Test running SUBS task with start and end date."""
        with self.assertLogs("subs.tasks", "INFO") as _logs:
            start_date = self.dh.yesterday
            end_date = self.dh.today
            collect_subs_cur_data(start_date, end_date)

            self.assertIn(f"Running SUBS task. Start-date: {start_date}. End-date: {end_date}", _logs.output[0])

    def test_get_report_no_end_date(self):
        """Test running SUBS task with no end date."""
        with self.assertLogs("subs.tasks", "INFO") as _logs:
            start_date = self.dh.yesterday
            collect_subs_cur_data(start_date)

            self.assertIn(f"Running SUBS task. Start-date: {start_date}. End-date: ", _logs.output[0])
