#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import json

from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIClient

from api.settings.tags.mapping.query_handler import format_tag_mapping_relationship
from api.settings.tags.mapping.view import SettingsTagMappingFilter
from masu.test import MasuTestCase
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.all.models import TagMapping


class TestSettingsTagMappingView(MasuTestCase):
    def setUp(self):
        """Set up the tests."""
        super().setUp()
        self.client = APIClient()

        with tenant_context(self.tenant):
            self.enabled_uuid_list = list(EnabledTagKeys.objects.filter(enabled=True).values_list("uuid", flat=True))

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
        for item in response.data["data"]:
            self.assertEqual(item["source_type"], "AWS")
        # Check that the response data is filtered correctly (with OCP example)
        url = reverse("tags-mapping") + "?source_type=ocP"  # also testing case sensitivity
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["data"]:
            self.assertEqual(item["source_type"], "OCP")

    def test_get_child_tag_key(self):
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
        for item in response.data["data"]:
            self.assertEqual(item["source_type"], "AWS")

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
        for item in response.data["data"]:
            self.assertEqual(item["source_type"], "AWS")

    def test_put_method_invalid_uuid(self):
        """Test the put method for the tag mapping view with an invalid uuid"""
        url = reverse("tags-mapping-child-add")
        data = {"parent": "29f738e4-38f4-4ed8-a9f4-beed48165220", "children": ["29f738e4-38f4-4ed8-a9f4-beed48165229"]}
        response = self.client.put(url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_method_validate_parent(self):
        """Test if a parent can be added as a child."""
        url = reverse("tags-mapping-child-add")
        data = {
            "parent": self.enabled_uuid_list[0],
            "children": [self.enabled_uuid_list[1], self.enabled_uuid_list[2], self.enabled_uuid_list[3]],
        }
        response = self.client.put(url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # Adding a parent as child
        data = {"parent": self.enabled_uuid_list[4], "children": [self.enabled_uuid_list[0]]}
        response = self.client.put(url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_method_validate_child(self):
        """Test if a child can be added as a parent."""
        url = reverse("tags-mapping-child-add")
        data = {
            "parent": self.enabled_uuid_list[0],
            "children": [self.enabled_uuid_list[1], self.enabled_uuid_list[2]],
        }
        response = self.client.put(url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # Adding a child as parent
        data = {"parent": self.enabled_uuid_list[2], "children": [self.enabled_uuid_list[4]]}
        response = self.client.put(url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Add one more additional child
        data = {
            "parent": self.enabled_uuid_list[0],
            "children": [self.enabled_uuid_list[1], self.enabled_uuid_list[2], self.enabled_uuid_list[3]],
        }
        response = self.client.put(url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_method_add_multiple_children(self):
        """Test adding multiple children (list)."""
        url = reverse("tags-mapping-child-add")
        data = {
            "parent": self.enabled_uuid_list[0],
            "children": [self.enabled_uuid_list[1], self.enabled_uuid_list[2]],
        }
        response = self.client.put(url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_put_method_remove_children(self):
        """Test removing children."""
        url = reverse("tags-mapping-child-add")
        data = {
            "parent": self.enabled_uuid_list[0],
            "children": [self.enabled_uuid_list[1], self.enabled_uuid_list[2], self.enabled_uuid_list[3]],
        }
        response = self.client.put(url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # Removing children
        url = reverse("tags-mapping-child-remove")
        data = {"ids": [self.enabled_uuid_list[1], self.enabled_uuid_list[3]]}
        response = self.client.put(url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_put_method_remove_parent(self):
        """Test removing parent."""
        url = reverse("tags-mapping-child-add")
        data = {
            "parent": self.enabled_uuid_list[0],
            "children": [self.enabled_uuid_list[1], self.enabled_uuid_list[2], self.enabled_uuid_list[3]],
        }
        response = self.client.put(url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # Removing parent
        url = reverse("tags-mapping-parent-remove")
        data = {"ids": [self.enabled_uuid_list[0]]}
        response = self.client.put(url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(response.data["detail"], "Parents deleted successfully.")

    def test_filter_by_source_type(self):
        """Test the filter by source_type."""
        # Get an already inserted provider type to check if the filter is working
        with tenant_context(self.tenant):
            url = reverse("tags-mapping-child-add")
            data = {
                "parent": self.enabled_uuid_list[0],
                "children": [self.enabled_uuid_list[1], self.enabled_uuid_list[2], self.enabled_uuid_list[3]],
            }
            response = self.client.put(url, data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            parent_provider_types = TagMapping.objects.values_list("parent__provider_type", flat=True).distinct()
            test_filter = parent_provider_types[0]
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            # Call the filter_by_source_type method with 'test_filter' as the value
            filter = SettingsTagMappingFilter()
            result = filter.filter_by_source_type(TagMapping.objects.all(), "provider_type", test_filter)
            self.assertNotEqual(len(result), 0)

            test_filter = "random"
            result = filter.filter_by_source_type(TagMapping.objects.all(), "provider_type", test_filter)
            self.assertEqual(len(result), 0)

    def test_format_tag_mapping_relationship(self):
        """Test the get method format for the tag mapping view"""

        sample_data = """{
            "meta": {
                "count": 3,
                "limit": 3,
                "offset": 0
            },
            "links": {
                "first": "/api/cost-management/v1/settings/tags/mappings/?limit=3&offset=0",
                "next": null,
                "previous": null,
                "last": "/api/cost-management/v1/settings/tags/mappings/?limit=3&offset=0"
            },
            "data": [
                {
                    "parent": {
                        "uuid": "17c77152-05a9-4b53-968c-dd42f7fd859b",
                        "key": "storageclass",
                        "source_type": "Azure"
                    },
                    "child": {
                        "uuid": "787d0e27-bf01-4f1e-91da-4148d9acae82",
                        "key": "environment",
                        "source_type": "Azure"
                    }
                },
                {
                    "parent": {
                        "uuid": "17c77152-05a9-4b53-968c-dd42f7fd859b",
                        "key": "storageclass",
                        "source_type": "Azure"
                    },
                    "child": {
                        "uuid": "09eae71b-4665-4958-9649-9031ee67180b",
                        "key": "CreatedOn",
                        "source_type": "OCI"
                    }
                },
                {
                    "parent": {
                        "uuid": "17c77152-05a9-4b53-968c-dd42f7fd859b",
                        "key": "storageclass",
                        "source_type": "Azure"
                    },
                    "child": {
                        "uuid": "00398f0a-bdb7-4fd3-841f-b9cd476cab7e",
                        "key": "free-tier-retained",
                        "source_type": "OCI"
                    }
                }
            ]
        }"""

        json_data = json.loads(sample_data)
        response = Response(json_data)
        result = format_tag_mapping_relationship(response)
        # Check if the key is 'children' and not 'child'
        for item in result.data["data"]:
            self.assertIn("children", item["parent"])
            self.assertNotIn("child", item["parent"])

    def test_filter_by_parent_and_child(self):
        """Test that you can filter by parent & child."""
        with tenant_context(self.tenant):
            child, parent = EnabledTagKeys.objects.all()[:2]
            url = reverse("tags-mapping-child-add")
            data = {
                "parent": str(parent.uuid),
                "children": [str(child.uuid)],
            }
            response = self.client.put(url, data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            url = reverse("tags-mapping") + f"?parent={parent.key}"
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            url = reverse("tags-mapping") + f"?child={child.key}"
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
