#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the source type mapping module."""
from django.test import TestCase

from api.provider.models import Provider
from sources.api.source_type_mapping import CMMO_ID_TO_PROVIDER_TYPE
from sources.api.source_type_mapping import CMMO_ID_TO_SOURCE_NAME
from sources.api.source_type_mapping import COST_MGMT_APP_TYPE_ID
from sources.api.source_type_mapping import get_cmmo_id
from sources.api.source_type_mapping import get_cmmo_id_by_name
from sources.api.source_type_mapping import get_provider_type
from sources.api.source_type_mapping import get_source_name
from sources.api.source_type_mapping import PROVIDER_TYPE_TO_CMMO_ID
from sources.api.source_type_mapping import SOURCE_NAME_TO_CMMO_ID


class SourceTypeMappingTest(TestCase):
    """Test Cases for source_type_mapping module."""

    def test_cost_mgmt_app_type_id(self):
        """Test COST_MGMT_APP_TYPE_ID is defined."""
        self.assertEqual(COST_MGMT_APP_TYPE_ID, "0")

    def test_cmmo_id_to_provider_type_mapping(self):
        """Test CMMO_ID_TO_PROVIDER_TYPE contains expected mappings."""
        self.assertEqual(CMMO_ID_TO_PROVIDER_TYPE["1"], Provider.PROVIDER_OCP)
        self.assertEqual(CMMO_ID_TO_PROVIDER_TYPE["2"], Provider.PROVIDER_AWS)
        self.assertEqual(CMMO_ID_TO_PROVIDER_TYPE["3"], Provider.PROVIDER_AZURE)
        self.assertEqual(CMMO_ID_TO_PROVIDER_TYPE["4"], Provider.PROVIDER_GCP)

    def test_provider_type_to_cmmo_id_mapping(self):
        """Test PROVIDER_TYPE_TO_CMMO_ID is the inverse of CMMO_ID_TO_PROVIDER_TYPE."""
        self.assertEqual(PROVIDER_TYPE_TO_CMMO_ID[Provider.PROVIDER_OCP], "1")
        self.assertEqual(PROVIDER_TYPE_TO_CMMO_ID[Provider.PROVIDER_AWS], "2")
        self.assertEqual(PROVIDER_TYPE_TO_CMMO_ID[Provider.PROVIDER_AZURE], "3")
        self.assertEqual(PROVIDER_TYPE_TO_CMMO_ID[Provider.PROVIDER_GCP], "4")

    def test_cmmo_id_to_source_name_mapping(self):
        """Test CMMO_ID_TO_SOURCE_NAME contains expected mappings."""
        self.assertEqual(CMMO_ID_TO_SOURCE_NAME["1"], "openshift")
        self.assertEqual(CMMO_ID_TO_SOURCE_NAME["2"], "amazon")
        self.assertEqual(CMMO_ID_TO_SOURCE_NAME["3"], "azure")
        self.assertEqual(CMMO_ID_TO_SOURCE_NAME["4"], "google")

    def test_source_name_to_cmmo_id_mapping(self):
        """Test SOURCE_NAME_TO_CMMO_ID is the inverse of CMMO_ID_TO_SOURCE_NAME."""
        self.assertEqual(SOURCE_NAME_TO_CMMO_ID["openshift"], "1")
        self.assertEqual(SOURCE_NAME_TO_CMMO_ID["amazon"], "2")
        self.assertEqual(SOURCE_NAME_TO_CMMO_ID["azure"], "3")
        self.assertEqual(SOURCE_NAME_TO_CMMO_ID["google"], "4")

    def test_get_provider_type_valid(self):
        """Test get_provider_type with valid CMMO IDs."""
        test_cases = [
            ("1", Provider.PROVIDER_OCP),
            ("2", Provider.PROVIDER_AWS),
            ("3", Provider.PROVIDER_AZURE),
            ("4", Provider.PROVIDER_GCP),
        ]
        for cmmo_id, expected in test_cases:
            with self.subTest(cmmo_id=cmmo_id):
                self.assertEqual(get_provider_type(cmmo_id), expected)

    def test_get_provider_type_invalid(self):
        """Test get_provider_type with invalid CMMO ID returns None."""
        self.assertIsNone(get_provider_type("999"))
        self.assertIsNone(get_provider_type(""))
        self.assertIsNone(get_provider_type("invalid"))

    def test_get_cmmo_id_valid(self):
        """Test get_cmmo_id with valid provider types."""
        test_cases = [
            (Provider.PROVIDER_OCP, "1"),
            (Provider.PROVIDER_AWS, "2"),
            (Provider.PROVIDER_AZURE, "3"),
            (Provider.PROVIDER_GCP, "4"),
        ]
        for provider_type, expected in test_cases:
            with self.subTest(provider_type=provider_type):
                self.assertEqual(get_cmmo_id(provider_type), expected)

    def test_get_cmmo_id_invalid(self):
        """Test get_cmmo_id with invalid provider type returns None."""
        self.assertIsNone(get_cmmo_id("INVALID"))
        self.assertIsNone(get_cmmo_id(""))

    def test_get_source_name_valid(self):
        """Test get_source_name with valid CMMO IDs."""
        test_cases = [
            ("1", "openshift"),
            ("2", "amazon"),
            ("3", "azure"),
            ("4", "google"),
        ]
        for cmmo_id, expected in test_cases:
            with self.subTest(cmmo_id=cmmo_id):
                self.assertEqual(get_source_name(cmmo_id), expected)

    def test_get_source_name_invalid(self):
        """Test get_source_name with invalid CMMO ID returns None."""
        self.assertIsNone(get_source_name("999"))
        self.assertIsNone(get_source_name(""))

    def test_get_cmmo_id_by_name_valid(self):
        """Test get_cmmo_id_by_name with valid source names."""
        test_cases = [
            ("openshift", "1"),
            ("amazon", "2"),
            ("azure", "3"),
            ("google", "4"),
        ]
        for name, expected in test_cases:
            with self.subTest(name=name):
                self.assertEqual(get_cmmo_id_by_name(name), expected)

    def test_get_cmmo_id_by_name_invalid(self):
        """Test get_cmmo_id_by_name with invalid source name returns None."""
        self.assertIsNone(get_cmmo_id_by_name("invalid"))
        self.assertIsNone(get_cmmo_id_by_name(""))
