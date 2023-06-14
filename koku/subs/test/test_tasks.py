#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the SUBS task."""
from unittest import mock

from subs.tasks import collect_subs_report_data
from subs.tasks import collect_subs_report_data_from_manifest
from subs.test import SUBSTestCase


class TestSUBSTasks(SUBSTestCase):
    """Test cases for SUBS Celery tasks."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()

    @mock.patch("subs.tasks.enable_subs_processing")
    @mock.patch("subs.tasks.get_providers_for_subs")
    def test_collect_subs_report_data_from_manifest(self, mock_get_providers, mock_enable_processing):
        # Mock the necessary dependencies and inputs
        provider_list = [
            {"provider_type": self.aws_provider_type, "provider_uuid": self.aws_provider_uuid},
            # Add more provider data as needed
        ]
        mock_get_providers.return_value = provider_list
        mock_enable_processing.return_value = True

        # Call the task function
        collect_subs_report_data_from_manifest([])

        # Perform assertions or checks on the expected behavior and outcomes
        # mock_get_providers.assert_called_once_with()
        # mock_enable_processing.assert_called_once_with(schema_name)

    @mock.patch("subs.tasks.enable_subs_processing")
    def test_collect_subs_report_data(self, mock_enable_processing):
        # Mock the necessary dependencies and inputs

        mock_enable_processing.return_value = True

        # Call the task function
        collect_subs_report_data(self, self.schema_name, self.aws_provider_type, self.aws_provider_uuid)

        # Perform assertions or checks on the expected behavior and outcomes
        # mock_get_providers.assert_called_once_with()
        # mock_enable_processing.assert_called_once_with(schema_name)
