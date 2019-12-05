#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
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
        self.assertEqual(self.schema, accessor.get_schema_name())
