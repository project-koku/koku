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

"""Test the ProviderDBAccessor utility object."""

from masu.external import AMAZON_WEB_SERVICES
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.customer_db_accessor import CustomerDBAccessor
from tests import MasuTestCase


class ProviderDBAccessorTest(MasuTestCase):
    """Test Cases for the ProviderDBAccessor object."""

    def setUp(self):
        pass

    def test_initializer(self):
        """Test Initializer"""
        uuid = '6e212746-484a-40cd-bba0-09a19d132d64'
        accessor = ProviderDBAccessor(uuid)
        self.assertIsNotNone(accessor._session)
        self.assertTrue(accessor.does_db_entry_exist())

    def test_get_uuid(self):
        """Test uuid getter."""
        uuid = '6e212746-484a-40cd-bba0-09a19d132d64'
        accessor = ProviderDBAccessor(uuid)
        self.assertEqual(uuid, accessor.get_uuid())

    def test_get_provider_name(self):
        """Test provider name getter."""
        uuid = '6e212746-484a-40cd-bba0-09a19d132d64'
        accessor = ProviderDBAccessor(uuid)
        self.assertEqual('Test Provider', accessor.get_provider_name())

    def test_get_type(self):
        """Test provider type getter."""
        uuid = '6e212746-484a-40cd-bba0-09a19d132d64'
        accessor = ProviderDBAccessor(uuid)
        self.assertEqual(AMAZON_WEB_SERVICES, accessor.get_type())

    def test_get_authentication(self):
        """Test provider authentication getter."""
        uuid = '6e212746-484a-40cd-bba0-09a19d132d64'
        expected_auth_string = 'arn:aws:iam::111111111111:role/CostManagement'
        accessor = ProviderDBAccessor(uuid)
        self.assertEqual(expected_auth_string, accessor.get_authentication())

    def test_get_billing_source(self):
        """Test provider billing_source getter."""
        uuid = '6e212746-484a-40cd-bba0-09a19d132d64'
        expected_billing_source = 'test-bucket'
        accessor = ProviderDBAccessor(uuid)
        self.assertEqual(expected_billing_source, accessor.get_billing_source())

    def test_get_customer_uuid(self):
        """Test provider billing_source getter."""
        uuid = '6e212746-484a-40cd-bba0-09a19d132d64'
        accessor = ProviderDBAccessor(uuid)
        customer = CustomerDBAccessor(1)
        expected_uuid = customer.get_uuid()
        self.assertEqual(expected_uuid, accessor.get_customer_uuid())

    def test_get_customer(self):
        """Test provider customer getter."""
        uuid = '6e212746-484a-40cd-bba0-09a19d132d64'
        expected_customer_name = 'Test Customer'
        accessor = ProviderDBAccessor(uuid)
        self.assertEqual(expected_customer_name, accessor.get_customer())
