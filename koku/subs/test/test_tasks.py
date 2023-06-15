#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the SUBS task."""
from unittest.mock import patch

from subs.tasks import collect_subs_report_data
from subs.tasks import collect_subs_report_data_from_manifest
from subs.test import SUBSTestCase


class TestSUBSTasks(SUBSTestCase):
    """Test cases for SUBS Celery tasks."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()

    @patch("subs.tasks.collect_subs_report_data")
    @patch("subs.tasks.enable_subs_processing")
    def test_collect_subs_report_data_from_manifest(self, mock_enable_processing, *args):

        # Mock the necessary dependencies and inputs
        mock_enable_processing.return_value = True

        # Call the task function
        collect_subs_report_data_from_manifest([])

        # Perform assertions or checks on the expected behavior and outcomes
        # mock_enable_processing.assert_called_once_with(schema_name)

    def test_collect_subs_report_data(self):

        # Call the task function
        collect_subs_report_data(self.schema_name, self.aws_provider_type, self.aws_provider_uuid)

        # Perform assertions or checks on the expected behavior and outcomes
