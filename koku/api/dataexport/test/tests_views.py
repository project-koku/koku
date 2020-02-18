"""Collection of tests for customer-initiated data export requests API."""
from unittest.mock import patch

from django.urls import reverse
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase


class DataExportRequestViewSetTest(IamTestCase):
    """DataExportRequestViewSet test case."""

    @patch("api.dataexport.serializers.sync_data_to_customer")
    def test_second_request_with_same_dates_fails(self, mock_sync):
        """
        Test saving a request and then the same request again.

        We expect the first request to succeed and the second to fail.
        This prevents the customer from overwhelming the export process with
        unnecessary requests.
        """
        start_date = "2019-01-01"
        end_date = "2019-02-01"
        post_data = {"start_date": start_date, "end_date": end_date, "bucket_name": "my-test-bucket"}

        url = reverse("dataexportrequests-list")
        client = APIClient()
        # First request should succeed.
        response = client.post(url, data=post_data, **self.headers)
        self.assertEqual(response.status_code, 201)
        response_json = response.json()
        self.assertEqual(response_json["start_date"], start_date)
        self.assertEqual(response_json["end_date"], end_date)
        self.assertEqual(response_json["status"], "pending")
        self.assertEqual(response_json["bucket_name"], "my-test-bucket")

        # Second request should fail.
        response = client.post(url, data=post_data, **self.headers)
        self.assertEqual(response.status_code, 400)
        response_json = response.json()
        self.assertEqual(len(response_json["errors"]), 1)
        error = response_json["errors"][0]
        self.assertEqual(error["status"], 400)
        self.assertEqual(error["source"], "non_field_errors")

    def test_end_date_before_start_date_fails(self):
        """Test refusing a request with end date before start date."""
        start_date = "2019-02-01"
        end_date = "2019-01-01"
        post_data = {"start_date": start_date, "end_date": end_date, "bucket_name": "my-test-bucket"}

        url = reverse("dataexportrequests-list")
        client = APIClient()

        response = client.post(url, data=post_data, **self.headers)
        self.assertEqual(response.status_code, 400)
        response_json = response.json()
        self.assertEqual(len(response_json["errors"]), 2)
        errors = response_json["errors"]
        sources = {errors[0]["source"], errors[1]["source"]}
        self.assertEqual(errors[0]["status"], 400)
        self.assertEqual(errors[0]["status"], 400)
        self.assertEqual(sources, {"start_date", "end_date"})
