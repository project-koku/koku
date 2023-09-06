import rest_framework.test
from django.urls import reverse
from django_tenants.utils import schema_context
from rest_framework import status

from api.iam.test.iam_test_case import IamTestCase


class TestAWSCostCategoriesAPI(IamTestCase):
    def test_aws_category_keys_get(self):
        """Basic test to exercise the API endpoint"""
        url = reverse("settings-aws-category-keys")
        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()
            response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_aws_category_keys_enable(self):
        """Basic test to exercise the API endpoint"""
        url = reverse("settings-aws-category-keys-enable")
        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()
            response = client.put(url, {"ids": []}, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_aws_category_keys_disable(self):
        """Basic test to exercise the API endpoint"""
        url = reverse("settings-aws-category-keys-disable")
        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()
            response = client.put(url, {"ids": []}, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
