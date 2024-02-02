import random

from django.urls import reverse
from faker import Faker
from rest_framework import status
from api.iam.test.iam_test_case import IamTestCase
from rest_framework.test import APIClient

from reporting.provider.all.models import EnabledTagKeys
from django_tenants.utils import tenant_context


class SettingsTagMappingViewTestCase(IamTestCase):

    def setUp(self):
        """Set up the tests."""
        super().setUp()
        self.client = APIClient()

        # Create some sample data
        cloud_providers = ["AWS", "Azure", "GCP", "OCP"]
        fake = Faker()

        for _ in range(30):
            tag_key = EnabledTagKeys(
                key=fake.uuid4(),
                enabled=True,
                provider_type=random.choice(cloud_providers)
            )
            with tenant_context(self.tenant):
                tag_key.save()

    def test_get_method(self):
        """Test the get method for the tag mapping view"""
        url = reverse("tags-mapping")
        response = self.client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_method_with_filter(self):
        """Test the get method for the tag mapping view with a filter"""

        # Check that the response data is filtered correctly (with AWS example)
        url = reverse("tags-mapping") + "?source_type=aWs"  # also testing case sensitivity
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for item in response.data['data']:
            self.assertEqual(item['source_type'], 'AWS')

        # Check that the response data is filtered correctly (with OCP example)
        url = reverse("tags-mapping") + "?source_type=ocP"  # also testing case sensitivity
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for item in response.data['data']:
            self.assertEqual(item['source_type'], 'OCP')

    def test_get_child(self):
        """Test the get method for the tag mapping Child view"""
        url = reverse("tags-mapping-child")
        response = self.client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_child_with_filter(self):
        """Test the get method for the tag mapping Child view with a filter"""
        url = reverse("tags-mapping-child") + "?source_type=aWs"
        response = self.client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check that the response data is filtered correctly
        for item in response.data['data']:
            self.assertEqual(item['source_type'], 'AWS')

    def test_get_parent(self):
        """Test the get method for the tag mapping Parent view"""
        url = reverse("tags-mapping-parent")
        response = self.client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_parent_with_filter(self):
        """Test the get method for the tag mapping Parent view with a filter"""
        url = reverse("tags-mapping-parent") + "?source_type=aWs"
        response = self.client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check that the response data is filtered correctly
        for item in response.data['data']:
            self.assertEqual(item['source_type'], 'AWS')

    def test_put_method_invalid_uuid(self):
        """Test the put method for the tag mapping view with an invalid uuid"""
        url = reverse("tags-mapping-child-add")
        data = {"parent": "29f738e4-38f4-4ed8-a9f4-beed48165220", "children": ["29f738e4-38f4-4ed8-a9f4-beed48165229"]}

        response = self.client.put(url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_method_validate_parent(self):
        """Test if a parent can be added as a child."""
        url = reverse("tags-mapping-child-add")

        # Adding sample uuids
        random_uuid_list = self.retrieve_sample_uuids()
        url = reverse("tags-mapping-child-add")
        data = {"parent": random_uuid_list[0],
                "children": [random_uuid_list[1], random_uuid_list[2], random_uuid_list[3]]}
        response = self.client.put(url, data, format="json", **self.headers)

        if response.status_code == status.HTTP_200_OK:
            # Adding a parent as child
            data = {"parent": random_uuid_list[4], "children": [random_uuid_list[0]]}
            response = self.client.put(url, data, format="json", **self.headers)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_method_validate_child(self):
        """Test if a child can be added as a parent."""

        # Adding sample uuids
        random_uuid_list = self.retrieve_sample_uuids()
        url = reverse("tags-mapping-child-add")
        data = {"parent": random_uuid_list[0],
                "children": [random_uuid_list[1], random_uuid_list[2], random_uuid_list[3]]}
        response = self.client.put(url, data, format="json", **self.headers)

        if response.status_code == status.HTTP_200_OK:
            # Adding a child as parent
            data = {"parent": random_uuid_list[2], "children": [random_uuid_list[4]]}
            response = self.client.put(url, data, format="json", **self.headers)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_method_add_multiple_children(self):
        """Test adding multiple children (list)."""
        random_uuid_list = self.retrieve_sample_uuids()
        url = reverse("tags-mapping-child-add")
        data = {"parent": random_uuid_list[0], "children": [random_uuid_list[1], random_uuid_list[2]]}

        response = self.client.put(url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_put_method_remove_children(self):
        """Test removing children."""

        # Adding sample uuids
        random_uuid_list = self.retrieve_sample_uuids()
        url = reverse("tags-mapping-child-add")
        data = {"parent": random_uuid_list[0],
                "children": [random_uuid_list[1], random_uuid_list[2], random_uuid_list[3]]}
        response = self.client.put(url, data, format="json", **self.headers)

        if response.status_code == status.HTTP_200_OK:
            # Removing children
            url = reverse("tags-mapping-child-remove")
            data = {"ids": [random_uuid_list[1], random_uuid_list[3]]}
            response = self.client.put(url, data, format="json", **self.headers)

            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_put_method_remove_parent(self):
        """Test removing parent."""

        # Adding sample uuids
        random_uuid_list = self.retrieve_sample_uuids()
        url = reverse("tags-mapping-child-add")
        data = {"parent": random_uuid_list[0],
                "children": [random_uuid_list[1], random_uuid_list[2], random_uuid_list[3]]}
        response = self.client.put(url, data, format="json", **self.headers)

        if response.status_code == status.HTTP_200_OK:
            # Removing parent
            url = reverse("tags-mapping-parent-remove")
            data = {"ids": [random_uuid_list[0]]}
            response = self.client.put(url, data, format="json", **self.headers)

            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def retrieve_sample_uuids(self):
        """Gets all inserted uuids to use on adding(put) methods."""
        with tenant_context(self.tenant):
            enabled_tag_keys = EnabledTagKeys.objects.all()
            uuid_list = [tag_key.uuid for tag_key in enabled_tag_keys]

        return uuid_list
