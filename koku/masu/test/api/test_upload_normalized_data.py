"""Test the upload_normalized_data API view."""
import uuid
from unittest.mock import patch

from celery.result import AsyncResult
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from rest_framework import status


@override_settings(ROOT_URLCONF="masu.urls")
class UploadNormalizedDataViewTest(TestCase):
    """Test Cases for the upload_normalized_data API."""

    @patch("masu.celery.tasks.upload_normalized_data.delay")
    def test_upload_normalized_data_post(self, mock_delay):
        """Assert upload_normalized_data POST returns expected data."""
        result_id = str(uuid.uuid4())
        mock_delay.return_value = AsyncResult(result_id)
        url = reverse("upload_normalized_data")
        response = self.client.post(url)

        mock_delay.assert_called_once_with()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertDictEqual(body, {"AsyncResult ID": result_id})

    @patch("masu.celery.tasks.upload_normalized_data.delay")
    def test_upload_normalized_data_get_not_allowed(self, mock_delay):
        """Assert upload_normalized_data GET is not allowed."""
        url = reverse("upload_normalized_data")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        mock_delay.assert_not_called()
