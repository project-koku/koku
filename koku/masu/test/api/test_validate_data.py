#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the validate data endpoint."""
import uuid
from unittest.mock import patch

from django.test.utils import override_settings
from django.urls import reverse

from masu.test import MasuTestCase


@override_settings(ROOT_URLCONF="masu.urls")
class ValidateDataViewTest(MasuTestCase):
    """Test Cases for the validate data API."""

    def setUp(self):
        """Create test case setup."""
        super().setUp()

    @patch("koku.middleware.MASU", return_value=True)
    def test_validate_data(self, _):
        """Test validate data endpoint."""
        expected_key = "Error"
        url = reverse("validate_cost_data")
        # test missing start date
        response = self.client.get(url)
        body = response.json()
        self.assertEqual(response.status_code, 400)
        self.assertIn("start_date is a required parameter.", body[expected_key])

        # test missing end date
        url_w_params = url + "?start_date=2021-04-01"
        response = self.client.get(url_w_params)
        body = response.json()
        self.assertEqual(response.status_code, 400)
        self.assertIn("end_date is a required parameter.", body[expected_key])

        # test missing provider uuid
        url_w_params = url + "?start_date=2021-04-01&end_date=2021-04-30"
        response = self.client.get(url_w_params)
        body = response.json()
        self.assertEqual(response.status_code, 400)
        self.assertIn("provider_uuid must be supplied as a parameter.", body[expected_key])

        # test provider does not exist
        id = str(uuid.uuid4())
        url_w_params = url + f"?start_date=2021-04-01&end_date=2021-04-30&provider_uuid={id}"
        response = self.client.get(url_w_params)
        body = response.json()
        self.assertEqual(response.status_code, 400)
        self.assertIn(f"provider_uuid {id} does not exist.", body[expected_key])

        # test non ocp provider with ocp on cloud type
        id = self.aws_provider_uuid
        url_w_params = url + f"?start_date=2021-04-01&end_date=2021-04-30&provider_uuid={id}&ocp_on_cloud_type=GCP"
        response = self.client.get(url_w_params)
        body = response.json()
        self.assertEqual(response.status_code, 400)
        self.assertIn("ocp_on_cloud_type must by used with an ocp provider.", body[expected_key])

        # test fake ocp on cloud type
        id = self.ocp_provider_uuid
        url_w_params = url + f"?start_date=2021-04-01&end_date=2021-04-30&provider_uuid={id}&ocp_on_cloud_type=OCP"
        response = self.client.get(url_w_params)
        body = response.json()
        self.assertEqual(response.status_code, 400)
        self.assertIn("ocp on cloud type must match:", body[expected_key])

        # test invalid queue
        url_w_params = url + f"?start_date=2021-04-01&end_date=2021-04-30&provider_uuid={id}&queue=test"
        response = self.client.get(url_w_params)
        body = response.json()
        self.assertEqual(response.status_code, 400)
        self.assertIn("'queue' must be one of", body[expected_key])
