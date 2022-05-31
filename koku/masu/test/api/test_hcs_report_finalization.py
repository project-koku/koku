#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the hcs_report_data endpoint view."""
import uuid
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse


@override_settings(ROOT_URLCONF="masu.urls")
class HCSFinalizationTests(TestCase):
    """Test Cases for the hcs_report_finalization endpoint."""

    ENDPOINT = "hcs_report_finalization"

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.hcs_report_finalization.collect_hcs_report_finalization")
    def test_get_report_data(self, mock_celery, _):
        """Test the GET report_data endpoint."""

        params = {
            "tracing_id": str(uuid.uuid4()),
        }
        expected_key = "HCS Report Finalization Task ID"

        response = self.client.get(reverse(self.ENDPOINT), params)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_celery.s.assert_called()
