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
        data = {"parent": "29f738e4-38f4-4ed8-a9f4-beed48165220", "child": "29f738e4-38f4-4ed8-a9f4-beed48165229"}

        response = self.client.put(url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_method_validate_parent(self):
        """Test if a parent can be added as a child."""
        url = reverse("tags-mapping-child-add")

        # Adding sample uuids
        data = {"parent": "f08751bf-e104-4813-bd48-dd46d98ce9cc", "children": ["1b78ba6d-e933-47d5-b99b-4261e2508162"]}
        response = self.client.put(url, data, format="json", **self.headers)

        # Adding a parent as child
        data = {"parent": "29f738e4-38f4-4ed8-a9f4-beed48165222", "children": ["f08751bf-e104-4813-bd48-dd46d98ce9cc"]}
        response = self.client.put(url, data, format="json", **self.headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_method_validate_child(self):
        """Test if a child can be added as a parent."""
        url = reverse("tags-mapping-child-add")

        # Adding sample uuids
        data = {"parent": "f08751bf-e104-4813-bd48-dd46d98ce9cc", "children": ["1b78ba6d-e933-47d5-b99b-4261e2508162"]}
        response = self.client.put(url, data, format="json", **self.headers)

        # Adding a child as parent
        data = {"parent": "1b78ba6d-e933-47d5-b99b-4261e2508162", "children": ["29f738e4-38f4-4ed8-a9f4-beed48165222"]}
        response = self.client.put(url, data, format="json", **self.headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_method_add_multiple_children(self):
        """Test adding multiple children (list)."""
        url = reverse("tags-mapping-child-add")
        data = {"parent": "f08751bf-e104-4813-bd48-dd46d98ce9cc", "children": ["1b78ba6d-e933-47d5-b99b-4261e2508162",
                                                                               "649908c9-49a6-4f3f-9c2d-663d1adf60b0"]}
        response = self.client.put(url, data, format="json", **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_put_method_remove_children(self):
        """Test removing children."""

        # Adding sample uuids
        url = reverse("tags-mapping-child-add")
        data = {"parent": "f08751bf-e104-4813-bd48-dd46d98ce9cc", "children": ["1b78ba6d-e933-47d5-b99b-4261e2508162",
                                                                               "649908c9-49a6-4f3f-9c2d-663d1adf60b0",
                                                                               "8437233a-cbb2-4472-937f-381cc56dfec6"]}
        response = self.client.put(url, data, format="json", **self.headers)

        # Removing children
        url = reverse("tags-mapping-child-remove")
        data = {"ids": ["1b78ba6d-e933-47d5-b99b-4261e2508162", "649908c9-49a6-4f3f-9c2d-663d1adf60b0"]}
        response = self.client.put(url, data, format="json", **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_put_method_remove_parent(self):
        """Test removing children."""

        # Adding sample uuids
        url = reverse("tags-mapping-child-add")
        data = {"parent": "f08751bf-e104-4813-bd48-dd46d98ce9cc", "children": ["1b78ba6d-e933-47d5-b99b-4261e2508162",
                                                                               "649908c9-49a6-4f3f-9c2d-663d1adf60b0",
                                                                               "8437233a-cbb2-4472-937f-381cc56dfec6"]}
        response = self.client.put(url, data, format="json", **self.headers)

        # Removing parent
        url = reverse("tags-mapping-parent-remove")
        data = {"ids": ["f08751bf-e104-4813-bd48-dd46d98ce9cc"]}
        response = self.client.put(url, data, format="json", **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
