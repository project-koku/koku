#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Report Views."""
import uuid
from unittest.mock import patch

from django.urls import reverse
from faker import Faker
from rest_framework import status
from rest_framework.test import APIClient

from api.provider.models import Provider
from api.utils import DateHelper
from masu.database.ingress_report_db_accessor import IngressReportDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase

FAKE = Faker()


class ReportsViewTest(MasuTestCase):
    """report view test cases."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.schema = self.schema_name
        self.dh = DateHelper()
        self.start = DateAccessor().today_with_timezone("UTC").replace(day=1)
        self.gcp_provider = Provider.objects.filter(type=Provider.PROVIDER_GCP_LOCAL).first()
        self.ingress_report_dict = {
            "uuid": str(uuid.uuid4()),
            "created_timestamp": self.start,
            "completed_timestamp": None,
            "reports_list": ["test"],
            "source": self.gcp_provider,
            "bill_year": self.dh.bill_year_from_date(self.dh.this_month_start),
            "bill_month": self.dh.bill_month_from_date(self.dh.this_month_start),
        }
        ingress_report_accessor = IngressReportDBAccessor(self.schema)
        self.added_ingress_report = ingress_report_accessor.add(**self.ingress_report_dict)

    def test_get_view(self):
        """Test to get posted reports."""
        url = reverse("reports")
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_source_view(self):
        """Test to get reports for a particular source."""
        url = f"/api/v1/ingress/reports/{self.gcp_provider.uuid}/"
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json().get("data")[0].get("source"), str(self.gcp_provider.uuid))

    def test_get_invalid_uuid_reports(self):
        """Test to get reports for a invalid source."""
        url = "/api/v1/ingress/reports/invalid/"
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_non_existant_source_reports(self):
        """Test to get reports for a non existant source."""
        url = f"/api/v1/ingress/reports/{self.ingress_report_dict.get('uuid')}/"
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

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

    @patch(
        "providers.aws.provider._get_sts_access",
        return_value=dict(
            aws_access_key_id=FAKE.md5(), aws_secret_access_key=FAKE.md5(), aws_session_token=FAKE.md5()
        ),
    )
    def test_post_ingress_reports_invalid_uuid(self, mock_get_sts_access):
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

    @patch(
        "providers.aws.provider._get_sts_access",
        return_value=dict(
            aws_access_key_id=FAKE.md5(), aws_secret_access_key=FAKE.md5(), aws_session_token=FAKE.md5()
        ),
    )
    def test_post_ingress_reports(self, mock_get_sts_access):
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
