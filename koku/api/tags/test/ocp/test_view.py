#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCP tag view."""
import calendar
from urllib.parse import quote_plus
from urllib.parse import urlencode

from dateutil.relativedelta import relativedelta
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions
from api.utils import DateHelper
from reporting.models import OCPStorageVolumeLabelSummary
from reporting.models import OCPUsageLineItemDailySummary
from reporting.models import OCPUsagePodLabelSummary


class OCPTagsViewTest(IamTestCase):
    """Tests the report view."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        cls.dh = DateHelper()
        cls.ten_days_ago = cls.dh.n_days_ago(cls.dh._now, 9)

    def _calculate_expected_range(self, time_scope_value, time_scope_units):
        today = self.dh.today

        if time_scope_value == "-1" and time_scope_units == "month":
            start_range = today.replace(day=1).date()
        elif time_scope_value == "-2" and time_scope_units == "month":
            start_range = (today - relativedelta(months=1)).replace(day=1).date()
        elif time_scope_value == "-10" and time_scope_units == "day":
            start_range = (today - relativedelta(days=10)).date()
        elif time_scope_value == "-30" and time_scope_units == "day":
            start_range = (today - relativedelta(days=30)).date()

        end_range = today.replace(day=calendar.monthrange(today.year, today.month)[1]).date()

        return start_range, end_range

    def test_execute_ocp_tags_queries_keys_only(self):
        """Test that tag key data is for the correct time queries."""
        test_cases = [
            {"value": "-1", "unit": "month", "resolution": "monthly", "enabled": False},
            {"value": "-2", "unit": "month", "resolution": "monthly", "enabled": False},
            {"value": "-10", "unit": "day", "resolution": "daily", "enabled": False},
            {"value": "-30", "unit": "day", "resolution": "daily", "enabled": False},
            {"value": "-1", "unit": "month", "resolution": "monthly", "enabled": True},
            {"value": "-2", "unit": "month", "resolution": "monthly", "enabled": True},
            {"value": "-10", "unit": "day", "resolution": "daily", "enabled": True},
            {"value": "-30", "unit": "day", "resolution": "daily", "enabled": True},
        ]

        for case in test_cases:
            url = reverse("openshift-tags")
            client = APIClient()
            params = {
                "filter[resolution]": case.get("resolution"),
                "filter[time_scope_value]": case.get("value"),
                "filter[time_scope_units]": case.get("unit"),
                "key_only": True,
                "filter[enabled]": case.get("enabled"),
            }
            url = url + "?" + urlencode(params, quote_via=quote_plus)
            response = client.get(url, **self.headers)

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()

            if not case.get("enabled"):
                self.assertTrue(data.get("data"))
            self.assertTrue(isinstance(data.get("data"), list))

    def test_execute_ocp_tags_queries(self):
        """Test that tag data is for the correct time queries."""
        test_cases = [
            {"value": "-1", "unit": "month", "resolution": "monthly"},
            {"value": "-2", "unit": "month", "resolution": "monthly"},
            {"value": "-10", "unit": "day", "resolution": "daily"},
            {"value": "-30", "unit": "day", "resolution": "daily"},
        ]

        for case in test_cases:
            url = reverse("openshift-tags")
            client = APIClient()
            params = {
                "filter[resolution]": case.get("resolution"),
                "filter[time_scope_value]": case.get("value"),
                "filter[time_scope_units]": case.get("unit"),
                "key_only": False,
                "filter[enabled]": False,
            }
            url = url + "?" + urlencode(params, quote_via=quote_plus)
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()

            for tag in data.get("data"):
                self.assertIsNotNone(tag.get("values"))

            self.assertTrue(data.get("data"))
            self.assertTrue(isinstance(data.get("data"), list))

    def test_execute_ocp_tags_type_queries(self):
        """Test that tag data is for the correct type queries."""
        test_cases = [
            {"value": "-1", "unit": "month", "resolution": "monthly", "type": "pod"},
            {"value": "-2", "unit": "month", "resolution": "monthly", "type": "pod"},
            {"value": "-10", "unit": "day", "resolution": "daily", "type": "pod"},
            {"value": "-30", "unit": "day", "resolution": "daily", "type": "storage"},
            {"value": "-10", "unit": "day", "resolution": "daily", "type": "*"},
        ]

        for case in test_cases:
            url = reverse("openshift-tags")
            client = APIClient()
            params = {
                "filter[resolution]": case.get("resolution"),
                "filter[time_scope_value]": case.get("value"),
                "filter[time_scope_units]": case.get("unit"),
                "key_only": False,
                "filter[type]": case.get("type"),
                "filter[enabled]": True,
            }
            url = url + "?" + urlencode(params, quote_via=quote_plus)
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()

            for tag in data.get("data"):
                self.assertIsNotNone(tag.get("values"))

            self.assertTrue(data.get("data"))
            self.assertTrue(isinstance(data.get("data"), list))

    def test_execute_query_with_and_filter(self):
        """Test the filter[and:] param in the view."""
        url = reverse("openshift-tags")
        client = APIClient()

        with tenant_context(self.tenant):
            projects = (
                OCPUsageLineItemDailySummary.objects.filter(usage_start__gte=self.ten_days_ago)
                .values("namespace")
                .distinct()
            )
            projects = [project.get("namespace") for project in projects]
        params = {
            "filter[resolution]": "daily",
            "filter[time_scope_value]": "-10",
            "filter[time_scope_units]": "day",
            "filter[and:project]": projects,
        }
        url = url + "?" + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_data = response.json()
        self.assertEqual(response_data.get("data", []), [])

    @RbacPermissions(
        {
            "openshift.cluster": {"read": ["*"]},
            "openshift.project": {"read": ["banking"]},
            "openshift.node": {"read": ["*"]},
        }
    )
    def test_rbac_ocp_tags(self):
        """Test that appropriate tag values are returned when data is restricted by namespace."""
        with tenant_context(self.tenant):
            banking_storage_tags = (
                OCPStorageVolumeLabelSummary.objects.filter(namespace="banking").values("key").distinct().all()
            )
            banking_usage_tags = (
                OCPUsagePodLabelSummary.objects.filter(namespace="banking").values("key").distinct().all()
            )
            tag_keys = [tag.get("key") for tag in banking_storage_tags] + [
                tag.get("key") for tag in banking_usage_tags
            ]

        url = reverse("openshift-tags")
        client = APIClient()
        params = {"key_only": False, "filter[enabled]": False}
        url = url + "?" + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        for tag in data.get("data"):
            self.assertIn(tag.get("key"), tag_keys)

    def test_cluster_filter(self):
        """Test that appropriate tag values are returned when data is filtered by cluster."""
        url = reverse("openshift-tags")
        client = APIClient()
        params = {"key_only": False, "filter[enabled]": False, "filter[cluster]": "OCP-on-AWS"}
        url = url + "?" + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        with tenant_context(self.tenant):
            cluster_storage_tags = (
                OCPStorageVolumeLabelSummary.objects.filter(report_period__cluster_id__contains="OCP-on-AWS")
                .values("key")
                .distinct()
                .all()
            )
            cluster_usage_tags = (
                OCPUsagePodLabelSummary.objects.filter(report_period__cluster_id__contains="OCP-on-AWS")
                .values("key")
                .distinct()
                .all()
            )
            tag_keys = [tag.get("key") for tag in cluster_storage_tags] + [
                tag.get("key") for tag in cluster_usage_tags
            ]
        for tag in data.get("data"):
            self.assertIn(tag.get("key"), tag_keys)
