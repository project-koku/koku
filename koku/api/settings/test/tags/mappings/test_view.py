#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging
from collections import defaultdict
from unittest.mock import patch

from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.test import APIClient

from api.provider.models import Provider
from api.settings.tags.mapping.query_handler import Relationship
from api.settings.tags.mapping.utils import retrieve_tag_rate_mapping
from api.settings.tags.mapping.view import SettingsTagMappingFilter
from masu.test import MasuTestCase
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.all.models import TagMapping

LOG = logging.getLogger(__name__)


class TestSettingsTagMappingView(MasuTestCase):
    def setUp(self):
        """Set up the tests."""
        super().setUp()
        self.client = APIClient()

        with tenant_context(self.tenant):
            self.enabled_uuid_list = list(EnabledTagKeys.objects.filter(enabled=True).values_list("uuid", flat=True))
        self.tag_mapping_url = reverse("tags-mapping")
        self.parent_get_url = reverse("tags-mapping-parent")
        self.parent_remove_url = reverse("tags-mapping-parent-remove")
        self.child_get_url = reverse("tags-mapping-child")
        self.child_add_url = reverse("tags-mapping-child-add")
        self.child_remove_url = reverse("tags-mapping-child-remove")

    def test_get_method(self):
        """Test the get method for the tag mapping view"""
        for url in [self.tag_mapping_url, self.parent_get_url, self.child_get_url]:
            with self.subTest(url=url):
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_method_with_filter(self):
        """Test the get method for the tag mapping view with a filter"""
        # Check that the response data is filtered correctly (with AWS example)
        url = self.tag_mapping_url + "?source_type=aWs"  # also testing case sensitivity
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["data"]:
            self.assertEqual(item["source_type"], "AWS")
        # Check that the response data is filtered correctly (with OCP example)
        url = self.tag_mapping_url + "?source_type=ocP"  # also testing case sensitivity
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["data"]:
            self.assertEqual(item["source_type"], "OCP")

    def test_get_child_with_filter(self):
        """Test the get method for the tag mapping Child view with a filter"""
        url = self.child_get_url + "?source_type=aWs"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check that the response data is filtered correctly
        for item in response.data["data"]:
            self.assertEqual(item["source_type"], "AWS")

    def test_put_method_invalid_uuid(self):
        """Test the put method for the tag mapping view with an invalid uuid"""
        data = {"parent": "29f738e4-38f4-4ed8-a9f4-beed48165220", "children": ["29f738e4-38f4-4ed8-a9f4-beed48165229"]}
        response = self.client.put(self.child_add_url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_method_validate_parent(self):
        """Test if a parent can be added as a child."""
        data = {
            "parent": self.enabled_uuid_list[0],
            "children": [self.enabled_uuid_list[1], self.enabled_uuid_list[2], self.enabled_uuid_list[3]],
        }
        response = self.client.put(self.child_add_url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # Adding a parent as child
        data = {"parent": self.enabled_uuid_list[4], "children": [self.enabled_uuid_list[0]]}
        response = self.client.put(self.child_add_url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_method_validate_child(self):
        """Test if a child can be added as a parent."""
        data = {
            "parent": self.enabled_uuid_list[0],
            "children": [self.enabled_uuid_list[1], self.enabled_uuid_list[2]],
        }
        response = self.client.put(self.child_add_url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # Adding a child as parent
        data = {"parent": self.enabled_uuid_list[2], "children": [self.enabled_uuid_list[4]]}
        response = self.client.put(self.child_add_url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Add one more additional child
        data = {
            "parent": self.enabled_uuid_list[0],
            "children": [self.enabled_uuid_list[1], self.enabled_uuid_list[2], self.enabled_uuid_list[3]],
        }
        response = self.client.put(self.child_add_url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_method_add_multiple_children(self):
        """Test adding multiple children (list)."""
        data = {
            "parent": self.enabled_uuid_list[0],
            "children": [self.enabled_uuid_list[1], self.enabled_uuid_list[2]],
        }
        response = self.client.put(self.child_add_url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_put_method_remove_children(self):
        """Test removing children."""
        data = {
            "parent": self.enabled_uuid_list[0],
            "children": [self.enabled_uuid_list[1], self.enabled_uuid_list[2], self.enabled_uuid_list[3]],
        }
        response = self.client.put(self.child_add_url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # Removing children
        data = {"ids": [self.enabled_uuid_list[1], self.enabled_uuid_list[3]]}
        response = self.client.put(self.child_remove_url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_put_method_remove_parent(self):
        """Test removing parent."""
        data = {
            "parent": self.enabled_uuid_list[0],
            "children": [self.enabled_uuid_list[1], self.enabled_uuid_list[2], self.enabled_uuid_list[3]],
        }
        response = self.client.put(self.child_add_url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # Removing parent
        data = {"ids": [self.enabled_uuid_list[0]]}
        response = self.client.put(self.parent_remove_url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_filter_by_source_type(self):
        """Test the filter by source_type."""
        # Get an already inserted provider type to check if the filter is working
        with tenant_context(self.tenant):
            data = {
                "parent": self.enabled_uuid_list[0],
                "children": [self.enabled_uuid_list[1], self.enabled_uuid_list[2], self.enabled_uuid_list[3]],
            }
            response = self.client.put(self.child_add_url, data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            parent_provider_types = TagMapping.objects.values_list("parent__provider_type", flat=True).distinct()
            test_filter = parent_provider_types[0]
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            # Call the filter_by_source_type method with 'test_filter' as the value
            filter = SettingsTagMappingFilter()
            result = filter.filter_by_source_type(TagMapping.objects.all(), "parent__provider_type", test_filter)
            self.assertNotEqual(len(result), 0)

            filter = "?filter[source_type]=random"
            url = self.tag_mapping_url + filter
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(response.data["data"]), 0)

    def test_format_tag_mapping_relationship(self):
        """Test the get method format for the tag mapping view"""

        sample_data = [
            # Parent with three children
            {
                "child": {
                    "key": "environment",
                    "source_type": "Azure",
                    "uuid": "787d0e27-bf01-4f1e-91da-4148d9acae82",
                },
                "parent": {
                    "key": "storageclass",
                    "source_type": "Azure",
                    "uuid": "17c77152-05a9-4b53-968c-dd42f7fd859b",
                },
            },
            {
                "child": {
                    "key": "CreatedOn",
                    "source_type": "OCI",
                    "uuid": "09eae71b-4665-4958-9649-9031ee67180b",
                },
                "parent": {
                    "key": "storageclass",
                    "source_type": "Azure",
                    "uuid": "17c77152-05a9-4b53-968c-dd42f7fd859b",
                },
            },
            {
                "child": {
                    "key": "free-tier-retained",
                    "source_type": "OCI",
                    "uuid": "00398f0a-bdb7-4fd3-841f-b9cd476cab7e",
                },
                "parent": {
                    "key": "storageclass",
                    "source_type": "Azure",
                    "uuid": "17c77152-05a9-4b53-968c-dd42f7fd859b",
                },
            },
            # Parent with two children
            {
                "child": {
                    "uuid": "135ed068-18cb-44fe-8d1c-1e7f389bcbe8",
                    "key": "openshift_project",
                    "source_type": "AWS",
                },
                "parent": {
                    "key": "stack",
                    "source_type": "AWS",
                    "uuid": "1ab796d3-37ac-4ae5-b218-688ea3b5a5f4",
                },
            },
            {
                "child": {
                    "uuid": "e789bbc7-e2b7-45f6-b611-e90dd2e0749e",
                    "key": "com_REDHAT_rhel",
                    "source_type": "AWS",
                },
                "parent": {
                    "key": "stack",
                    "source_type": "AWS",
                    "uuid": "1ab796d3-37ac-4ae5-b218-688ea3b5a5f4",
                },
            },
        ]

        relationships = Relationship.create_list_of_relationships(sample_data)

        self.assertTrue(
            all(getattr(relationship, "children", None) for relationship in relationships), "Missing children"
        )
        self.assertFalse(
            any(getattr(relationship, "child", None) for relationship in relationships), "Child key should not exist"
        )
        self.assertEqual(
            [len(relationship.children) for relationship in relationships],
            [3, 2],
            "Number of expected children is incorrect",
        )

    @patch("api.settings.tags.mapping.utils.get_cached_tag_rate_map")
    def test_cached_tag_rate_mapping(self, mock_get):
        tag_rate_map = {"Nilla": "Sushi"}
        mock_get.return_value = tag_rate_map
        return_value = retrieve_tag_rate_mapping(self.schema_name)
        self.assertEqual(tag_rate_map, return_value)

    def test_removal_of_unmapped_key(self):
        """Test that we error when we try to remove an unmapped key."""
        for url in [self.parent_remove_url, self.child_remove_url]:
            with self.subTest(url=url):
                data = {"ids": [self.enabled_uuid_list[0]]}
                response = self.client.put(url, data, format="json", **self.headers)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("api.settings.tags.mapping.view.retrieve_tag_rate_mapping")
    def test_adding_a_child_connected_to_a_cost_model(self, mock_tag_rates):
        """Test that you are not allowed to add a child connected to a cost model."""

        with tenant_context(self.tenant):
            enabled_row = EnabledTagKeys.objects.get(uuid=self.enabled_uuid_list[1])
            mock_tag_rates.return_value = {
                enabled_row.key: {
                    "provider_uuid": "6cb85968-06bc-4347-b...a46bed185b",
                    "cost_model_id": "91417cce-4b66-4b41-8...137bdb1620",
                },
                "application": {
                    "provider_uuid": "6cb85968-06bc-4347-b...a46bed185b",
                    "cost_model_id": "91417cce-4b66-4b41-8...137bdb1620",
                },
                "instance-type": {
                    "provider_uuid": "6cb85968-06bc-4347-b...a46bed185b",
                    "cost_model_id": "91417cce-4b66-4b41-8...137bdb1620",
                },
            }
            data = {
                "parent": self.enabled_uuid_list[0],
                "children": [str(self.enabled_uuid_list[1])],
            }
            response = self.client.put(self.child_add_url, data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_child_returns_400(self):
        """Test empty child returns 400"""
        data = {"parent": self.enabled_uuid_list[0], "children": []}
        response = self.client.put(self.child_add_url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_parent_and_child(self):
        """Test that you can filter by parent & child."""
        with tenant_context(self.tenant):
            child, parent = EnabledTagKeys.objects.all()[:2]
            data = {
                "parent": str(parent.uuid),
                "children": [str(child.uuid)],
            }
            response = self.client.put(self.child_add_url, data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            url = self.tag_mapping_url + f"?parent={parent.key}"
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            url = self.tag_mapping_url + f"?child={child.key}"
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_order_by_fake_value(self):
        """Test the get method for the tag mapping view"""
        url = self.tag_mapping_url + "?order_by[parent]=FAKE"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_multi_source_type_filter(self):
        """Test multiple source type filters."""
        source_type_mapping = defaultdict(list)
        enabled_keys = EnabledTagKeys.objects.filter(enabled=True)
        for enabled_key in enabled_keys:
            source_type_mapping[enabled_key.provider_type].append(enabled_key.uuid)
        aws_uuids = source_type_mapping.get(Provider.PROVIDER_AWS)
        azure_uuids = source_type_mapping.get(Provider.PROVIDER_AZURE)
        ocp_uuids = source_type_mapping.get(Provider.PROVIDER_OCP)
        body_metadata = [
            {"parent": ocp_uuids[0], "children": [azure_uuids[0]]},
            {"parent": aws_uuids[1], "children": [azure_uuids[1]]},
            {"parent": azure_uuids[1], "children": [azure_uuids[3]]},
        ]
        for data in body_metadata:
            response = self.client.put(self.child_add_url, data, format="json", **self.headers)
        # Test multiple source_type filters
        test_matrix = [
            f"?filter[source_type]={Provider.PROVIDER_AWS}&filter[source_type]={Provider.PROVIDER_AZURE}",
            f"?filter[source_type]={Provider.PROVIDER_AWS}&filter[source_type]={Provider.PROVIDER_OCP}",
        ]
        for multi_filter in test_matrix:
            for url in [self.child_get_url, self.tag_mapping_url]:
                with self.subTest(multi_filter=multi_filter, url=url):
                    filtered_url = url + multi_filter
                    response = self.client.get(filtered_url, **self.headers)
                    self.assertEqual(response.status_code, status.HTTP_200_OK)
                    self.assertNotEqual(len(response.data["data"]), 0)

    def test_multi_key_filter(self):
        """Test multiple source type filters."""
        enabled_keys = EnabledTagKeys.objects.filter(enabled=True)
        test_matrix = [
            f"?filter[key]={enabled_keys[0].key}&filter[key]={enabled_keys[4].key}",
            f"?filter[key]={enabled_keys[1].key}&filter[key]={enabled_keys[3].key}",
        ]
        for multi_filter in test_matrix:
            for url in [self.parent_get_url, self.child_get_url]:
                with self.subTest(multi_filter=multi_filter, url=url):
                    filtered_url = url + multi_filter
                    response = self.client.get(filtered_url, **self.headers)
                    self.assertEqual(response.status_code, status.HTTP_200_OK)
                    self.assertNotEqual(len(response.data["data"]), 0)

    def test_multi_key_parent_and_child_filter(self):
        """Test that you can filter by parent & child keys."""
        enabled_keys = EnabledTagKeys.objects.filter(enabled=True)
        test_populate = [
            {"parent": enabled_keys[0].uuid, "children": [enabled_keys[1].uuid, enabled_keys[2].uuid]},
            {"parent": enabled_keys[3].uuid, "children": [enabled_keys[4].uuid, enabled_keys[5].uuid]},
        ]
        for populate in test_populate:
            self.client.put(self.child_add_url, populate, format="json", **self.headers)
        # test parent filter
        test_matrix = [
            ("parent", enabled_keys[0].key, enabled_keys[3].key),
            ("child", enabled_keys[1].key, enabled_keys[5].key),
        ]
        for test in test_matrix:
            filter_key, key_one, key_two = test
            filter = f"?filter[{filter_key}]={key_one}&filter[{filter_key}]={key_two}"
            url = self.tag_mapping_url + filter
            with self.subTest(url=url):
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertNotEqual(len(response.data["data"]), 0)

    def test_deduplicate_and_unify_parent_keys(self):
        """Test that we have deduplicated app keys."""
        key = "test_deduplication"
        providers = [Provider.PROVIDER_AWS, Provider.PROVIDER_AZURE, Provider.PROVIDER_GCP]
        parent_keys = [EnabledTagKeys(key=key, enabled=True, provider_type=provider) for provider in providers]
        with tenant_context(self.tenant):
            EnabledTagKeys.objects.bulk_create(parent_keys)
        url = self.parent_get_url + f"?filter[key]={key}"
        response = self.client.get(url, **self.headers)
        self.assertEqual(len(response.data.get("data")), 1)
        # Test unification under one parent key
        test_populate = [
            {"parent": parent_keys[0].uuid, "children": [self.enabled_uuid_list[0]]},
            {"parent": parent_keys[1].uuid, "children": [self.enabled_uuid_list[1]]},
            {"parent": parent_keys[2].uuid, "children": [self.enabled_uuid_list[2]]},
        ]
        for populate in test_populate:
            self.client.put(self.child_add_url, populate, format="json", **self.headers)
        url = self.tag_mapping_url + f"?filter[parent]={key}"
        response = self.client.get(url, **self.headers)
        data = response.data.get("data")
        self.assertEqual(len(data), 1)
        data_dict = data[0]
        self.assertTrue(len(data_dict.get("children")), len(test_populate))
