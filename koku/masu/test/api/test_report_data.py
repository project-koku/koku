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
"""Test the report_data endpoint view."""
import datetime
from unittest.mock import patch
from urllib.parse import urlencode

from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from api.models import Provider
from masu.processor.tasks import OCP_QUEUE
from masu.processor.tasks import PRIORITY_QUEUE
from masu.processor.tasks import QUEUE_LIST


@override_settings(ROOT_URLCONF="masu.urls")
class ReportDataTests(TestCase):
    """Test Cases for the report_data endpoint."""

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.ProviderDBAccessor")
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data(self, mock_update, mock_accessor, _):
        """Test the GET report_data endpoint."""
        provider_type = Provider.PROVIDER_AWS
        mock_accessor.return_value.__enter__.return_value.get_type.return_value = provider_type
        start_date = datetime.date.today()
        params = {
            "schema": "acct10001",
            "start_date": start_date,
            "provider_uuid": "6e212746-484a-40cd-bba0-09a19d132d64",
        }
        expected_key = "Report Data Task ID"

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_update.s.assert_called_with(
            params["schema"],
            Provider.PROVIDER_AWS,
            params["provider_uuid"],
            str(params["start_date"]),
            None,
            queue_name=PRIORITY_QUEUE,
        )

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.ProviderDBAccessor")
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_sent_to_OCP_queue(self, mock_update, mock_accessor, _):
        """Test the GET report_data endpoint."""
        provider_type = Provider.PROVIDER_OCP
        mock_accessor.return_value.__enter__.return_value.get_type.return_value = provider_type
        start_date = datetime.date.today()
        params = {
            "schema": "acct10001",
            "start_date": start_date,
            "provider_uuid": "6e212746-484a-40cd-bba0-09a19d132d64",
            "queue": "ocp",
        }
        expected_key = "Report Data Task ID"

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_update.s.assert_called_with(
            params["schema"],
            Provider.PROVIDER_OCP,
            params["provider_uuid"],
            str(params["start_date"]),
            None,
            queue_name=OCP_QUEUE,
        )

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_schema_missing(self, mock_update, _):
        """Test GET report_data endpoint returns a 400 for missing schema."""
        start_date = datetime.date.today()
        params = {"start_date": start_date, "provider_uuid": "6e212746-484a-40cd-bba0-09a19d132d64"}
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
        start_date = datetime.date.today()
        params = {"start_date": start_date, "schema": "acct10001"}

        expected_key = "Error"
        expected_message = "provider_uuid or provider_type must be supplied as a parameter."

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_provider_invalid_uuid_(self, mock_update, _):
        """Test GET report_data endpoint returns a 400 for invalid provider_uuid."""
        start_date = datetime.date.today()
        params = {
            "start_date": start_date,
            "schema": "acct10001",
            "provider_uuid": "6e212746-484a-40cd-bba0-09a19d132ddd",
        }
        expected_key = "Error"
        expected_message = "Unable to determine provider type."

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_invalid_queue(self, mock_update, _):
        """Test GET report_data endpoint returns a 400 for invalid queue."""
        start_date = datetime.date.today()
        params = {
            "start_date": start_date,
            "schema": "acct10001",
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
        params = {"schema": "acct10001", "provider_uuid": "6e212746-484a-40cd-bba0-09a19d132d64"}
        expected_key = "Error"
        expected_message = "start_date is a required parameter."

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.ProviderDBAccessor")
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_mismatch_types_uuid(self, mock_update, mock_accessor, _):
        """Test GET report_data endpoint returns a 400 for mismatched type and uuid."""
        start_date = datetime.date.today()
        provider_type = Provider.PROVIDER_AWS
        mock_accessor.return_value.__enter__.return_value.get_type.return_value = provider_type
        params = {
            "schema": "acct10001",
            "provider_uuid": "6e212746-484a-40cd-bba0-09a19d132d64",
            "provider_type": Provider.PROVIDER_OCP,
            "start_date": start_date,
        }
        expected_key = "Error"
        expected_message = "provider_uuid and provider_type have mismatched provider types."

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.ProviderDBAccessor")
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_with_end_date(self, mock_update, mock_accessor, _):
        """Test GET report_data endpoint with end date."""
        start_date = datetime.date.today()
        end_date = start_date + datetime.timedelta(days=1)
        provider_type = Provider.PROVIDER_AWS
        mock_accessor.return_value.__enter__.return_value.get_type.return_value = provider_type
        params = {
            "schema": "acct10001",
            "provider_uuid": "6e212746-484a-40cd-bba0-09a19d132d64",
            "start_date": start_date,
            "end_date": end_date,
        }
        expected_key = "Report Data Task ID"

        response = self.client.get(reverse("report_data"), params)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_update.s.assert_called_with(
            params["schema"],
            provider_type,
            params["provider_uuid"],
            str(params["start_date"]),
            str(params["end_date"]),
            queue_name=PRIORITY_QUEUE,
        )

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_summary_tables")
    def test_get_report_data_with_only_provider_type(self, mock_update, _):
        """Test GET report_data endpoint with only provider_type."""
        start_date = datetime.date.today()
        end_date = start_date + datetime.timedelta(days=1)
        params = {
            "schema": "acct10001",
            "provider_type": Provider.PROVIDER_AWS,
            "start_date": start_date,
            "end_date": end_date,
        }
        expected_key = "Report Data Task ID"

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_update.s.assert_called_with(
            params["schema"],
            params["provider_type"],
            None,
            str(params["start_date"]),
            str(params["end_date"]),
            queue_name=PRIORITY_QUEUE,
        )

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.update_all_summary_tables")
    def test_get_report_data_for_all_providers(self, mock_update, _):
        """Test GET report_data endpoint with provider_uuid=*."""
        start_date = datetime.date.today()
        params = {"provider_uuid": "*", "start_date": start_date}
        expected_key = "Report Data Task ID"

        response = self.client.get(reverse("report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_update.delay.assert_called_with(str(params["start_date"]), None)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.remove_expired_data")
    def test_remove_report_data(self, mock_remove, _):
        """Test that the DELETE call to report_data works."""
        params = {
            "schema": "acct10001",
            "provider": Provider.PROVIDER_AWS,
            "provider_uuid": "6e212746-484a-40cd-bba0-09a19d132d64",
            "simulate": False,
        }
        query_string = urlencode(params)
        expected_key = "Report Data Task ID"

        url = reverse("report_data") + "?" + query_string
        response = self.client.delete(url)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_remove.delay.assert_called_with(
            params["schema"], params["provider"], params["simulate"], str(params["provider_uuid"])
        )

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.remove_expired_data")
    def test_remove_report_data_simulate(self, mock_remove, _):
        """Test that the DELETE call to report_data works."""
        params = {
            "schema": "acct10001",
            "provider": Provider.PROVIDER_AWS,
            "provider_uuid": "6e212746-484a-40cd-bba0-09a19d132d64",
            "simulate": True,
        }
        query_string = urlencode(params)
        expected_key = "Report Data Task ID"

        url = reverse("report_data") + "?" + query_string
        response = self.client.delete(url)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_remove.delay.assert_called_with(
            params["schema"], params["provider"], params["simulate"], str(params["provider_uuid"])
        )

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.remove_expired_data")
    def test_remove_report_data_simulate_missing(self, mock_remove, _):
        """Test that the DELETE call to report_data works."""
        params = {
            "schema": "acct10001",
            "provider": Provider.PROVIDER_AWS,
            "provider_uuid": "6e212746-484a-40cd-bba0-09a19d132d64",
        }
        query_string = urlencode(params)
        expected_key = "Report Data Task ID"

        url = reverse("report_data") + "?" + query_string
        response = self.client.delete(url)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_remove.delay.assert_called_with(params["schema"], params["provider"], False, str(params["provider_uuid"]))

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.remove_expired_data")
    def test_remove_report_data_schema_missing(self, mock_remove, _):
        """Test that the DELETE call to report_data works."""
        params = {
            "provider": Provider.PROVIDER_AWS,
            "provider_uuid": "6e212746-484a-40cd-bba0-09a19d132d64",
            "simulate": True,
        }
        query_string = urlencode(params)
        expected_key = "Error"
        expected_message = "schema is a required parameter."

        url = reverse("report_data") + "?" + query_string
        response = self.client.delete(url)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.remove_expired_data")
    def test_remove_report_data_provider_missing(self, mock_remove, _):
        """Test that the DELETE call to report_data works."""
        params = {"schema": "acct10001", "provider_uuid": "6e212746-484a-40cd-bba0-09a19d132d64", "simulate": True}
        query_string = urlencode(params)
        expected_key = "Error"
        expected_message = "provider is a required parameter."

        url = reverse("report_data") + "?" + query_string
        response = self.client.delete(url)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.report_data.remove_expired_data")
    def test_remove_report_data_provider_uuid_missing(self, mock_remove, _):
        """Test that the DELETE call to report_data works."""
        params = {"schema": "acct10001", "provider": Provider.PROVIDER_AWS, "simulate": True}
        query_string = urlencode(params)
        expected_key = "Error"
        expected_message = "provider_uuid is a required parameter."

        url = reverse("report_data") + "?" + query_string
        response = self.client.delete(url)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)
