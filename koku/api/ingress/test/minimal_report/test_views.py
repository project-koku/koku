#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Minimal Report Views."""
from django.urls import reverse
from faker import Faker
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider

FAKE = Faker()


class MinimalReportViewTest(IamTestCase):
    """Minimal report view test cases."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()

        self.aws_provider = Provider.objects.filter(type=Provider.PROVIDER_AWS_LOCAL).first()

        self.minimal_report = {
            "uuid": "8245313d-e61a-4c2a-91b2-92c1430c55c1",
            "created_timestamp": "2023-01-24T12:10:10.736585Z",
            "completed_timestamp": None,
            "reports_list": ["s3://my-bucket/January-2023-awscost.csv.gz"],
            "source": self.aws_provider.uuid,
        }

    def test_get_view(self):
        """Test that posted reports are viewable."""
        url = reverse("minimal-reports")
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
