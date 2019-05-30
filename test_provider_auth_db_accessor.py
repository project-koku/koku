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

"""Test the ProviderDBAuthAccessor utility object."""

from masu.database.provider_auth_db_accessor import ProviderAuthDBAccessor
from tests import MasuTestCase

class ProviderDBAuthAccessorTest(MasuTestCase):
    """Test Cases for the ProviderDBAuthAccessor object."""

    def test_initializer(self):
        """Test Initializer"""
        auth_id = self.aws_db_auth_id
        accessor = ProviderAuthDBAccessor(auth_id)
        self.assertIsNotNone(accessor._session)
        self.assertTrue(accessor.does_db_entry_exist())
        self.assertEqual(int(auth_id), accessor.get_auth_id())
        accessor.close_session()

    def test_initializer_provider_resource_name(self):
        """Test Initializer with provider resource name."""
        provider_resource_name = self.ocp_provider_resource_name
        accessor = ProviderAuthDBAccessor(provider_resource_name=provider_resource_name)
        self.assertIsNotNone(accessor._session)
        self.assertTrue(accessor.does_db_entry_exist())
        accessor.close_session()

    def test_initializer_auth_id_and_provider_resource_name(self):
        """Test Initializer with auth_id and provider resource name."""
        auth_id = self.ocp_db_auth_id
        provider_resource_name = self.ocp_provider_resource_name
        accessor = ProviderAuthDBAccessor(auth_id=auth_id, provider_resource_name=provider_resource_name)
        self.assertIsNotNone(accessor._session)
        self.assertTrue(accessor.does_db_entry_exist())
        self.assertEqual(int(auth_id), accessor.get_auth_id())
        accessor.close_session()

    def test_initializer_no_args(self):
        """Test Initializer with no arguments."""
        accessor = ProviderAuthDBAccessor()
        self.assertIsNotNone(accessor._session)
        self.assertTrue(accessor.does_db_entry_exist())
        accessor.close_session()

    def test_get_uuid(self):
        """Test uuid getter."""
        auth_id = self.aws_db_auth_id
        accessor = ProviderAuthDBAccessor(auth_id)
        self.assertEqual('7e4ec31b-7ced-4a17-9f7e-f77e9efa8fd6', accessor.get_uuid())
        accessor.close_session()

    def test_get_get_provider_resource_name(self):
        """Test provider name getter."""
        auth_id = self.aws_db_auth_id
        accessor = ProviderAuthDBAccessor(auth_id)
        self.assertEqual(self.aws_provider_resource_name, accessor.get_provider_resource_name())
        accessor.close_session()
