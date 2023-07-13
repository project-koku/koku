#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test SUBS Common Functions."""
import datetime
from unittest.mock import patch

from subs.common import enable_subs_processing
from subs.test import SUBSTestCase


class TestSUBSCommonFunctions(SUBSTestCase):
    """Test cases for SUBS Celery tasks."""

    def setUp(self):
        """Set up each test case."""
        super().setUp()

        self.start_date = self.dh.today - datetime.timedelta(days=2)
        self.end_date = self.dh.today

    @patch("subs.common.settings")
    def test_enable_subs_processing(self, mock_settings):
        mock_settings.ENABLE_SUBS_DEBUG = True

        result = enable_subs_processing(self.schema_name)

        self.assertTrue(result)
