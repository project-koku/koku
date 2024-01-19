from django.urls import reverse
from rest_framework import status
from api.iam.test.iam_test_case import IamTestCase
from rest_framework.test import APIClient


class SettingsTagMappingViewTestCase(IamTestCase):

    def setUp(self):
        """Set up the tests."""
        super().setUp()
        self.client = APIClient()

    def test_get_method(self):
        """Test the get method for the tag mapping view"""
        url = reverse("tags-mapping")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_put_method_invalid_uuid(self):
        """Test the put method for the tag mapping view with an invalid uuid"""
        url = reverse("tags-mapping-add")
        data = {"parent": "1816f1f8-b71c-49d9-8584-c781b95524de", "child": "553cf5b2-92a1-496a-bbaf-9fb470f17f00"}

        response = self.client.put(url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
