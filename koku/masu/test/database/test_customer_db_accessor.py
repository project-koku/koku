#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the CustomerDBAccessor utility object."""
from masu.database.customer_db_accessor import CustomerDBAccessor
from masu.test import MasuTestCase


class CustomerDBAccessorTest(MasuTestCase):
    """Test Cases for the CustomerDBAccessor object."""

    def test_initializer(self):
        """Test Initializer."""
        customer_id = self.customer.id
        accessor = CustomerDBAccessor(customer_id)
        self.assertTrue(accessor.does_db_entry_exist())

    def test_get_uuid(self):
        """Test uuid getter."""
        customer_id = self.customer.id
        accessor = CustomerDBAccessor(customer_id)
        self.assertIsNotNone(accessor.get_uuid())

    def test_get_schema_name(self):
        """Test provider name getter."""
        customer_id = self.customer.id
        accessor = CustomerDBAccessor(customer_id)
        self.assertEqual(self.schema_name, accessor.get_schema_name())
