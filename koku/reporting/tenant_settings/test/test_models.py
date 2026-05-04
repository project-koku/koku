#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the TenantSettings model."""
from django.core.exceptions import ValidationError
from django_tenants.utils import schema_context

from masu.test import MasuTestCase
from reporting.tenant_settings.models import TenantSettings


class TenantSettingsModelTest(MasuTestCase):
    """Tests for the TenantSettings model."""

    def setUp(self):
        """Clean tenant_settings before each test."""
        super().setUp()
        with schema_context(self.schema):
            TenantSettings.objects.all().delete()

    def test_table_exists_in_tenant_schema(self):
        """Verify migration created the table in the test tenant schema."""
        with schema_context(self.schema):
            self.assertEqual(TenantSettings.objects.count(), 0)

    def test_create_with_defaults(self):
        """A row with no explicit value gets the column default (3)."""
        with schema_context(self.schema):
            row = TenantSettings.objects.create()
            self.assertEqual(row.data_retention_months, TenantSettings.DEFAULT_RETENTION_MONTHS)

    def test_create_with_explicit_value(self):
        """An explicit value persists correctly."""
        with schema_context(self.schema):
            row = TenantSettings.objects.create(data_retention_months=24)
            row.refresh_from_db()
            self.assertEqual(row.data_retention_months, 24)

    def test_min_boundary_accepted(self):
        """The PRD minimum (3) passes model validation."""
        with schema_context(self.schema):
            row = TenantSettings(data_retention_months=3)
            row.full_clean()

    def test_max_boundary_accepted(self):
        """The upper limit (120) passes model validation."""
        with schema_context(self.schema):
            row = TenantSettings(data_retention_months=120)
            row.full_clean()

    def test_below_min_rejected(self):
        """Values below the PRD minimum are rejected by model validators."""
        with schema_context(self.schema):
            row = TenantSettings(data_retention_months=2)
            with self.assertRaises(ValidationError):
                row.full_clean()

    def test_above_max_rejected(self):
        """Values above the upper limit are rejected by model validators."""
        with schema_context(self.schema):
            row = TenantSettings(data_retention_months=121)
            with self.assertRaises(ValidationError):
                row.full_clean()

    def test_negative_value_rejected(self):
        """Negative values are rejected."""
        with schema_context(self.schema):
            row = TenantSettings(data_retention_months=-1)
            with self.assertRaises(ValidationError):
                row.full_clean()

    def test_zero_rejected(self):
        """Zero is rejected — must retain at least 3 months."""
        with schema_context(self.schema):
            row = TenantSettings(data_retention_months=0)
            with self.assertRaises(ValidationError):
                row.full_clean()

    def test_db_table_name(self):
        """Verify the DB table name matches the DDL specification."""
        self.assertEqual(TenantSettings._meta.db_table, "tenant_settings")
