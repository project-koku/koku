#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Report Views."""
import uuid
from unittest.mock import patch

from django.urls import reverse
from django_tenants.utils import schema_context
from faker import Faker
from model_bakery import baker
from rest_framework import status
from rest_framework.test import APIClient

from masu.test import MasuTestCase

FAKE = Faker()


class ReportsViewTest(MasuTestCase):
    """report view test cases."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.start = self.dh.this_month_start
        self.ingress_uuid = str(uuid.uuid4())

        for provider in [self.aws_provider, self.gcp_provider]:
            baker.make(
                "Sources",
                source_id=FAKE.pyint(),
                source_uuid=uuid.uuid4(),
                koku_uuid=provider.uuid,
                account_id=self.acct,
                org_id=self.org_id,
                source_type=provider.type,
                provider=provider,
                offset=FAKE.pyint(),
            )

        ingress_report_dict = {
            "uuid": self.ingress_uuid,
            "created_timestamp": self.start,
            "completed_timestamp": None,
            "reports_list": ["test"],
            "source": self.gcp_provider,
            "bill_year": self.dh.bill_year_from_date(self.dh.this_month_start),
            "bill_month": self.dh.bill_month_from_date(self.dh.this_month_start),
            "schema_name": self.customer,
        }
        with schema_context(self.schema):
            baker.make("IngressReports", **ingress_report_dict)

    def test_get_view(self):
        """Test to get posted reports."""
        url = reverse("reports")
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_source_view(self):
        """Test to get reports for a particular source."""
        url = f"{reverse('reports')}{self.gcp_provider.uuid}/"
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json().get("data")[0].get("source"), str(self.gcp_provider.uuid))

    def test_get_invalid_uuid_reports(self):
        """Test to get reports for a invalid source."""
        url = f"{reverse('reports')}invalid/"
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_non_existant_source_reports(self):
        """Test to get reports for a non existant source."""
        url = f"{reverse('reports')}{self.ingress_uuid}/"
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_post_invalid_ingress_reports(self):
        """Test to post invalid reports."""
        url = reverse("reports")
        post_data = {
            "source": str(self.aws_provider.uuid),
            "reports_list": "bad.csv",
            "bill_year": self.dh.bill_year_from_date(self.dh.this_month_start),
            "bill_month": self.dh.bill_month_from_date(self.dh.this_month_start),
        }
        client = APIClient()
        response = client.post(url, data=post_data, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_invalid_bill_dates(self):
        """Test to post invalid reports."""
        url = reverse("reports")
        post_data = {
            "source": str(self.aws_provider.uuid),
            "reports_list": ["test.csv", "test.csv"],
            "bill_year": "2022",
            "bill_month": "22",
        }
        client = APIClient()
        response = client.post(url, data=post_data, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("api.ingress.reports.serializers.ProviderAccessor.check_file_access")
    def test_post_ingress_reports_invalid_uuid(self, _):
        """Test to post reports for a particular source."""
        url = reverse("reports")
        post_data = {
            "source": "80ef",
            "reports_list": ["test.csv", "test.csv"],
            "bill_year": self.dh.bill_year_from_date(self.dh.this_month_start),
            "bill_month": self.dh.bill_month_from_date(self.dh.this_month_start),
        }
        client = APIClient()
        with patch("api.ingress.reports.view.Sources", side_affect=ValueError):
            response = client.post(url, data=post_data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("api.ingress.reports.serializers.ProviderAccessor.check_file_access")
    def test_post_ingress_reports(self, _):
        """Test to post reports for a particular source."""
        url = reverse("reports")
        post_data = {
            "source": f"{self.aws_provider.uuid}",
            "reports_list": ["test.csv", "test.csv"],
            "bill_year": self.dh.bill_year_from_date(self.dh.this_month_start),
            "bill_month": self.dh.bill_month_from_date(self.dh.this_month_start),
        }
        client = APIClient()
        response = client.post(url, data=post_data, format="json", **self.headers)
        self.assertEqual(response.json().get("data").get("source"), str(self.aws_provider.uuid))
        self.assertEqual(response.json().get("data").get("reports_list"), post_data.get("reports_list"))
