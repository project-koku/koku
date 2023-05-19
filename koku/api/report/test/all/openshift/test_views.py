#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCP on All Report views."""
from urllib.parse import quote_plus
from urllib.parse import urlencode

from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.utils import DateHelper
from reporting.models import OCPAWSCostLineItemDailySummaryP

URLS = [
    reverse("reports-openshift-all-costs"),
    reverse("reports-openshift-all-storage"),
    reverse("reports-openshift-all-instance-type"),
]

GROUP_BYS = ["project", "cluster", "node", "account", "region", "instance_type", "service", "product_family"]


class OCPAllReportViewTest(IamTestCase):
    """Tests the report view."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        cls.dh = DateHelper()
        cls.ten_days_ago = cls.dh.n_days_ago(cls.dh._now, 9)

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()

    def test_group_bys_with_second_group_by_tag(self):
        """Test that a group by project followed by a group by tag does not error."""
        with tenant_context(self.tenant):
            labels = (
                OCPAWSCostLineItemDailySummaryP.objects.filter(usage_start__gte=self.dh.last_month_start)
                .filter(usage_start__lte=self.dh.last_month_end)
                .values(*["tags"])
                .first()
            )
            tags = labels.get("tags")
            group_by_key = list(tags.keys())[0]

        client = APIClient()
        for url in URLS:
            for group_by in GROUP_BYS:
                params = {
                    "filter[resolution]": "monthly",
                    "filter[time_scope_value]": "-2",
                    "filter[time_scope_units]": "month",
                    f"group_by[{group_by}]": "*",
                    f"group_by[tag:{group_by_key}]": "*",
                }
                url = url + "?" + urlencode(params, quote_via=quote_plus)
                response = client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
