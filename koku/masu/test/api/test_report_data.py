#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the report_data endpoint view."""
import datetime
from unittest.mock import call
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from api.models import Provider
from api.utils import DateHelper
from common.queues import OCPQueue
from common.queues import PriorityQueue
from common.queues import QUEUE_LIST


@override_settings(ROOT_URLCONF="masu.urls")
class ReportDataTests(TestCase):
    """Test Cases for the report_data endpoint."""

    def setUp(self):
        """Create test case setup."""
        super().setUp()
        dh = DateHelper()
        self.start_date_time = dh.today.date()
        self.start_date = dh.today.date().strftime("%Y-%m-%d")
        self.invoice = dh.gcp_find_invoice_months_in_date_range(dh.today, dh.tomorrow)[0]

        self.provider_type = Provider.PROVIDER_AWS_LOCAL
        p = Provider.objects.filter(type=self.provider_type).first()
        self.provider_uuid = str(p.uuid)
        self.schema_name = p.account.get("schema_name")

        self.gcp_provider_type = Provider.PROVIDER_GCP_LOCAL
        gcp_p = Provider.objects.filter(type=self.gcp_provider_type).first()
        self.gcp_provider_uuid = str(gcp_p.uuid)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data(self, mock_update, _):
        """Test the GET report_data endpoint."""
        params = {
            "schema": self.schema_name,
            "start_date": self.start_date,
            "provider_uuid": self.provider_uuid,
        }
        expected_key = "Report Data Task IDs"

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_update.s.assert_called_with(
            params["schema"],
            self.provider_type,
            params["provider_uuid"],
            params["start_date"],
            DateHelper().today.date().strftime("%Y-%m-%d"),
            queue_name=PriorityQueue.DEFAULT,
            ocp_on_cloud=True,
            invoice_month=None,
        )

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_sent_to_OCP_queue(self, mock_update, _):
        """Test the GET report_data endpoint."""
        params = {
            "schema": self.schema_name,
            "start_date": self.start_date,
            "provider_uuid": self.provider_uuid,
            "queue": "ocp",
        }
        expected_key = "Report Data Task IDs"

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_update.s.assert_called_with(
            params["schema"],
            self.provider_type,
            params["provider_uuid"],
            params["start_date"],
            DateHelper().today.date().strftime("%Y-%m-%d"),
            queue_name=OCPQueue.DEFAULT,
            ocp_on_cloud=True,
            invoice_month=None,
        )

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_sent_to_XL_OCP_queue(self, mock_update, _):
        """Test the GET report_data using XL queue."""
        params = {
            "schema": self.schema_name,
            "start_date": self.start_date,
            "provider_uuid": self.provider_uuid,
        }
        expected_key = "Report Data Task IDs"

        with patch("masu.api.report_data.get_customer_queue", return_value=PriorityQueue.XL):
            response = self.client.get(reverse("report_data"), params)
            body = response.json()

            self.assertEqual(response.status_code, 200)
            self.assertIn(expected_key, body)
            mock_update.s.assert_called_with(
                params["schema"],
                self.provider_type,
                params["provider_uuid"],
                params["start_date"],
                DateHelper().today.date().strftime("%Y-%m-%d"),
                queue_name=PriorityQueue.XL,
                ocp_on_cloud=True,
                invoice_month=None,
            )

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_schema_missing(self, mock_update, _):
        """Test GET report_data endpoint returns a 400 for missing schema."""
        params = {"start_date": self.start_date, "provider_uuid": self.provider_uuid}
        expected_key = "Error"
        expected_message = "schema is a required parameter."

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_provider_uuid_missing(self, mock_update, _):
        """Test GET report_data endpoint returns a 400 for missing provider_uuid."""
        params = {"start_date": self.start_date, "schema": self.schema_name}

        expected_key = "Error"
        expected_message = "provider_uuid must be supplied as a parameter."

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_provider_invalid_uuid_(self, mock_update, _):
        """Test GET report_data endpoint returns a 400 for invalid provider_uuid."""
        params = {
            "start_date": self.start_date,
            "schema": self.schema_name,
            "provider_uuid": "6e212746-484a-40cd-bba0-09a19d132ddd",
        }
        expected_key = "Error"
        expected_message = "provider_uuid 6e212746-484a-40cd-bba0-09a19d132ddd does not exist"

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_provider_invalid_uuid_and_schema(self, mock_update, _):
        """Test GET report_data endpoint returns a 400 for invalid provider_uuid and schema."""
        params = {
            "start_date": self.start_date,
            "schema": "not-the-right-schema",
            "provider_uuid": self.provider_uuid,
        }
        expected_key = "Error"
        expected_message = f"provider_uuid {self.provider_uuid} is not associated with schema not-the-right-schema."

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_invalid_queue(self, mock_update, _):
        """Test GET report_data endpoint returns a 400 for invalid queue."""
        params = {
            "start_date": self.start_date,
            "schema": self.schema_name,
            "provider_uuid": "6e212746-484a-40cd-bba0-09a19d132ddd",
            "queue": "not-a-real-queue",
        }
        expected_key = "Error"
        expected_message = f"'queue' must be one of {QUEUE_LIST}."

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_date_missing(self, mock_update, _):
        """Test GET report_data endpoint returns a 400 for missing date."""
        params = {"schema": self.schema_name, "provider_uuid": self.provider_uuid}
        expected_key = "Error"
        expected_message = "start_date is a required parameter."

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_with_end_date(self, mock_update, _):
        """Test GET report_data endpoint with end date."""
        start_date = DateHelper().today
        end_date = start_date + datetime.timedelta(days=1)
        multiple_calls = start_date.month != end_date.month

        params = {
            "schema": self.schema_name,
            "provider_uuid": self.provider_uuid,
            "start_date": start_date.date().strftime("%Y-%m-%d"),
            "end_date": end_date.date().strftime("%Y-%m-%d"),
        }
        expected_key = "Report Data Task IDs"

        expected_calls = [
            call(
                params["schema"],
                self.provider_type,
                params["provider_uuid"],
                params["start_date"],
                params["end_date"],
                queue_name=PriorityQueue.DEFAULT,
                ocp_on_cloud=True,
                invoice_month=None,
            )
        ]

        if multiple_calls:
            expected_calls = [
                call(
                    params["schema"],
                    self.provider_type,
                    params["provider_uuid"],
                    params["start_date"],
                    params["start_date"],
                    queue_name=PriorityQueue.DEFAULT,
                    ocp_on_cloud=True,
                    invoice_month=None,
                ),
                call(
                    params["schema"],
                    self.provider_type,
                    params["provider_uuid"],
                    params["end_date"],
                    params["end_date"],
                    queue_name=PriorityQueue.DEFAULT,
                    ocp_on_cloud=True,
                    invoice_month=None,
                ),
            ]

        response = self.client.get(reverse("report_data"), params)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_update.s.assert_has_calls(expected_calls, any_order=True)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_ocp_on_cloud_false(self, mock_update, _):
        """Test the GET report_data endpoint."""
        params = {
            "schema": self.schema_name,
            "start_date": self.start_date,
            "provider_uuid": self.provider_uuid,
            "ocp_on_cloud": "false",
        }
        expected_key = "Report Data Task IDs"

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_update.s.assert_called_with(
            params["schema"],
            self.provider_type,
            params["provider_uuid"],
            params["start_date"],
            DateHelper().today.date().strftime("%Y-%m-%d"),
            queue_name=PriorityQueue.DEFAULT,
            ocp_on_cloud=False,
            invoice_month=None,
        )

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_gcp(self, mock_update, _):
        """Test the GET report_data endpoint."""
        params = {
            "schema": self.schema_name,
            "start_date": self.start_date,
            "provider_uuid": self.gcp_provider_uuid,
            "ocp_on_cloud": "false",
        }
        expected_key = "Report Data Task IDs"

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_update.s.assert_called_with(
            params["schema"],
            self.gcp_provider_type,
            params["provider_uuid"],
            params["start_date"],
            DateHelper().today.date().strftime("%Y-%m-%d"),
            queue_name=PriorityQueue.DEFAULT,
            ocp_on_cloud=False,
            invoice_month=self.invoice,
        )

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_gcp_end_date(self, mock_update, _):
        """Test the GET report_data endpoint."""
        params = {
            "schema": self.schema_name,
            "start_date": self.start_date,
            "end_date": self.start_date,
            "provider_uuid": self.gcp_provider_uuid,
            "ocp_on_cloud": "false",
        }
        expected_key = "Report Data Task IDs"

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_update.s.assert_called_with(
            params["schema"],
            self.gcp_provider_type,
            params["provider_uuid"],
            params["end_date"],
            DateHelper().today.date().strftime("%Y-%m-%d"),
            queue_name=PriorityQueue.DEFAULT,
            ocp_on_cloud=False,
            invoice_month=self.invoice,
        )

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_gcp_invoice_month(self, mock_update, _):
        """Test the GET report_data endpoint."""
        end_date = DateHelper().this_month_end.date().strftime("%Y-%m-%d")
        params = {
            "schema": self.schema_name,
            "start_date": self.start_date,
            "end_date": end_date,
            "provider_uuid": self.gcp_provider_uuid,
            "ocp_on_cloud": "false",
            "invoice_month": "202209",
        }
        expected_key = "Report Data Task IDs"

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_update.s.assert_called_with(
            params["schema"],
            self.gcp_provider_type,
            params["provider_uuid"],
            self.start_date,
            end_date,
            queue_name=PriorityQueue.DEFAULT,
            ocp_on_cloud=False,
            invoice_month="202209",
        )
