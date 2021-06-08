#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ProviderBillingSourceDBAccessor utility object."""
from masu.database.provider_billing_source_db_accessor import ProviderBillingSourceDBAccessor
from masu.test import MasuTestCase


class ProviderBillingSourceDBAccessorTest(MasuTestCase):
    """Test Cases for the ProviderBillingSourceDBAccessor object."""

    def test_initializer(self):
        """Test Initializer."""
        billing_source_id = self.aws_billing_source.id
        accessor = ProviderBillingSourceDBAccessor(billing_source_id)
        self.assertTrue(accessor.does_db_entry_exist())

    def test_get_uuid(self):
        """Test uuid getter."""
        billing_source_id = self.aws_billing_source.id
        accessor = ProviderBillingSourceDBAccessor(billing_source_id)
        self.assertEqual(str(self.aws_billing_source.uuid), accessor.get_uuid())

    def test_get_data_source(self):
        """Test provider name getter."""
        billing_source_id = self.aws_billing_source.id
        accessor = ProviderBillingSourceDBAccessor(billing_source_id)
        self.assertEqual(self.aws_billing_source.data_source, accessor.get_data_source())
