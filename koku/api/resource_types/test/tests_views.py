#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Test the Resource Types views."""
import logging
import random

from django.test import RequestFactory
from django.urls import reverse
from faker import Faker
from rest_framework import status
from rest_framework.test import APIClient
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from masu.test import MasuTestCase

FAKE = Faker()


class CostModelResourseTypesTest(MasuTestCase):
    """Test cases for the cost model resource type endpoint."""

    ENDPOINTS = ["cost-models"]

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        # Must set this to capture the logger messages in the tests.
        logging.disable(0)

    def setUp(self):
        """Set up the shared variables for each test case."""
        super().setUp()
        with tenant_context(self.tenant):
            self.cost_model = CostModel.objects.create(
                name=FAKE.word(), description=FAKE.word(), source_type=random.choice(Provider.PROVIDER_CHOICES)
            )
            self.cost_model_map = CostModelMap.objects.create(
                cost_model=self.cost_model, provider_uuid=self.aws_provider_uuid
            )

    def test_endpoint_view(self):
        """Test endpoint runs with a customer owner."""
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)
                self.assertTrue(len(json_result.get("data")) > 0)


class ResourceTypesViewTest(IamTestCase):
    """Tests the resource types views."""

    ENDPOINTS_RTYPE = ["resource-types"]
    ENDPOINTS_AWS = ["aws-accounts"]
    ENDPOINTS_AZURE = ["azure-subscription-guids"]
    ENDPOINTS_OPENSHIFT = ["openshift-clusters", "openshift-nodes", "openshift-projects"]
    ENDPOINTS = ENDPOINTS_RTYPE + ENDPOINTS_AWS + ENDPOINTS_AZURE + ENDPOINTS_OPENSHIFT

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.client = APIClient()
        self.factory = RequestFactory()

    def test_endpoint_view(self):
        """Test endpoint runs with a customer owner."""
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)
                self.assertTrue(len(json_result.get("data")) > 0)
