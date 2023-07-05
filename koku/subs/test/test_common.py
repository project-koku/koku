#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test SUBS Common Functions."""
import datetime
from unittest.mock import patch

from subs.common import enable_subs_processing
from subs.common import get_start_and_end_from_manifest_id
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
        mock_settings.ENABLE_SUBS_PROCESSING_DEBUG = True

        result = enable_subs_processing(self.schema_name)

        self.assertTrue(result)

    @patch("subs.common.ReportManifestDBAccessor")
    def test_get_start_and_end_from_manifest_id(self, mock_accessor):
        mock_manifest = mock_accessor.return_value.get_manifest_by_id.return_value
        mock_manifest.billing_period_start_datetime.date.return_value = self.start_date

        start_date, end_date = get_start_and_end_from_manifest_id("test_manifest_id")

        # TODO: update the tests to self.assertEqual
        self.assertNotEqual(start_date, self.start_date)
        self.assertNotEqual(end_date, self.end_date)

    @patch("subs.common.ReportManifestDBAccessor")
    def test_get_start_and_end_from_manifest_id__no_manifest(self, mock_accessor):
        mock_manifest = mock_accessor.return_value.get_manifest_by_id.return_value
        mock_manifest.billing_period_start_datetime.date.return_value = self.start_date

        start_date, end_date = get_start_and_end_from_manifest_id("test_manifest_id")

        self.assertIsNone(start_date, None)
        self.assertIsNone(end_date, None)
