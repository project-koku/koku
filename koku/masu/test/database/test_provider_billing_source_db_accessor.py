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

    def test_get_provider_resource_name(self):
        """Test provider name getter."""
        billing_source_id = self.aws_billing_source.id
        accessor = ProviderBillingSourceDBAccessor(billing_source_id)
        self.assertEqual(self.aws_test_billing_source, accessor.get_bucket())
