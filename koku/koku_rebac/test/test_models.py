#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for KesselSyncedResource model."""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "koku.test_settings_lite")

import django  # noqa: E402

django.setup()

from unittest.mock import MagicMock, patch  # noqa: E402

from django.test import SimpleTestCase  # noqa: E402


class TestKesselSyncedResourceImport(SimpleTestCase):
    """The model must be importable from koku_rebac.models."""

    def test_import(self):
        from koku_rebac.models import KesselSyncedResource

        self.assertIsNotNone(KesselSyncedResource)


class TestKesselSyncedResourceFields(SimpleTestCase):
    """Verify the model has the expected fields."""

    def test_has_resource_type_field(self):
        from koku_rebac.models import KesselSyncedResource

        field_names = [f.name for f in KesselSyncedResource._meta.get_fields()]
        self.assertIn("resource_type", field_names)

    def test_has_resource_id_field(self):
        from koku_rebac.models import KesselSyncedResource

        field_names = [f.name for f in KesselSyncedResource._meta.get_fields()]
        self.assertIn("resource_id", field_names)

    def test_has_org_id_field(self):
        from koku_rebac.models import KesselSyncedResource

        field_names = [f.name for f in KesselSyncedResource._meta.get_fields()]
        self.assertIn("org_id", field_names)

    def test_has_kessel_synced_field(self):
        from koku_rebac.models import KesselSyncedResource

        field_names = [f.name for f in KesselSyncedResource._meta.get_fields()]
        self.assertIn("kessel_synced", field_names)

    def test_has_last_synced_at_field(self):
        from koku_rebac.models import KesselSyncedResource

        field_names = [f.name for f in KesselSyncedResource._meta.get_fields()]
        self.assertIn("last_synced_at", field_names)

    def test_has_created_at_field(self):
        from koku_rebac.models import KesselSyncedResource

        field_names = [f.name for f in KesselSyncedResource._meta.get_fields()]
        self.assertIn("created_at", field_names)


class TestKesselSyncedResourceMeta(SimpleTestCase):
    """Verify model Meta options."""

    def test_db_table_name(self):
        from koku_rebac.models import KesselSyncedResource

        self.assertEqual(KesselSyncedResource._meta.db_table, "kessel_synced_resource")

    def test_unique_together_constraint(self):
        from koku_rebac.models import KesselSyncedResource

        self.assertIn(
            ("resource_type", "resource_id", "org_id"),
            KesselSyncedResource._meta.unique_together,
        )

    def test_str_representation(self):
        from koku_rebac.models import KesselSyncedResource

        obj = KesselSyncedResource(resource_type="cluster", resource_id="abc123", org_id="org1")
        result = str(obj)
        self.assertIn("cluster", result)
        self.assertIn("abc123", result)
        self.assertIn("org1", result)
