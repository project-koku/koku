#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from unittest.mock import patch

from django.urls import reverse
from django_tenants.utils import schema_context
from rest_framework.test import APIClient
from rest_framework.views import status

from api.iam.test.iam_test_case import IamTestCase


class OCPReportViewNetworkTest(IamTestCase):
    def test_network_api_access(self):
        url = reverse("reports-openshift-network")
        client = APIClient()
        with (
            schema_context(self.schema_name),
            patch(
                "api.report.ocp.view.UNLEASH_CLIENT.is_enabled",
                return_value=False,
            ),
        ):
            response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_network_api_access_dev(self):
        url = reverse("reports-openshift-network")
        client = APIClient()
        with (
            schema_context(self.schema_name),
            patch("api.report.ocp.view.UNLEASH_CLIENT.is_enabled", return_value=True),
        ):
            response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_network_api_group_by(self):
        url = reverse("reports-openshift-network")
        client = APIClient()
        with (
            schema_context(self.schema_name),
            patch(
                "api.report.ocp.view.UNLEASH_CLIENT.is_enabled",
                return_value=True,
            ),
        ):
            response = client.get(url, {"group_by[cluster]": "*"}, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["data"][0].get("clusters"))
