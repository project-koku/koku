#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCP-on-GCP Report views."""
# from urllib.parse import quote_plus
# from urllib.parse import urlencode
from django.test import RequestFactory
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.utils import DateHelper

# from django_tenants.utils import tenant_context
# from reporting.models import OCPGCPCostLineItemDailySummaryP

URLS = [
    reverse("reports-openshift-gcp-costs"),
    reverse("reports-openshift-gcp-storage"),
    reverse("reports-openshift-gcp-instance-type"),
]

GROUP_BYS = ["account", "region", "service", "project", "cluster", "node", "gcp_project"]


class OCPGCPReportViewTest(IamTestCase):
    """OCP on GCP report view test cases."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.client = APIClient()
        self.factory = RequestFactory()
        self.dh = DateHelper()

    def test_execute_query_w_delta_total(self):
        """Test that delta=total returns deltas."""
        query = "delta=cost"
        url = reverse("reports-openshift-gcp-costs") + "?" + query
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_execute_query_w_delta_bad_choice(self):
        """Test invalid delta value."""
        bad_delta = "Invalid"
        expected = f'"{bad_delta}" is not a valid choice.'
        query = f"delta={bad_delta}"
        url = reverse("reports-openshift-gcp-costs") + "?" + query
        response = self.client.get(url, **self.headers)
        result = str(response.data.get("delta")[0])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(result, expected)

    # Are we doing group by tag stuff?
    # def test_group_bys_with_second_group_by_tag(self):
    #     """Test that a group by project followed by a group by tag does not error."""
    #     with tenant_context(self.tenant):
    #         labels = (
    #             OCPGCPCostLineItemDailySummaryP.objects.filter(usage_start__gte=self.dh.last_month_start)
    #             .filter(usage_start__lte=self.dh.last_month_end)
    #             .values(*["tags"])
    #             .first()
    #         )

    #         tags = labels.get("tags")
    #         group_by_key = list(tags.keys())[0]

    #     client = APIClient()
    #     for url in URLS:
    #         for group_by in GROUP_BYS:
    #             params = {
    #                 "filter[resolution]": "monthly",
    #                 "filter[time_scope_value]": "-2",
    #                 "filter[time_scope_units]": "month",
    #                 f"group_by[{group_by}]": "*",
    #                 f"group_by[tag:{group_by_key}]": "*",
    #             }
    #             url = url + "?" + urlencode(params, quote_via=quote_plus)
    #             response = client.get(url, **self.headers)
    #             self.assertEqual(response.status_code, status.HTTP_200_OK)
