"""Collection of tests for customer-initiated data export requests API."""
from django.urls import reverse
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase


class DataExportRequestViewSetTest(IamTestCase):
    """DataExportRequestViewSet test case."""

    def test_end_date_before_start_date_fails(self):
        """Test refusing a request with end date before start date."""
        start_date = '2019-02-01'
        end_date = '2019-01-01'
        post_data = {'start_date': start_date, 'end_date': end_date}

        url = reverse('dataexportrequests-list')
        client = APIClient()

        response = client.post(url, data=post_data, **self.headers)
        self.assertEqual(response.status_code, 400)
        response_json = response.json()
        self.assertEqual(len(response_json['errors']), 2)
        errors = response_json['errors']
        sources = {errors[0]['source'], errors[1]['source']}
        self.assertEqual(errors[0]['status'], 400)
        self.assertEqual(errors[0]['status'], 400)
        self.assertEqual(sources, {'start_date', 'end_date'})
