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
from masu.test import MasuTestCase


class ProviderDBAuthAccessorTest(MasuTestCase):
    """Test Cases for the ProviderDBAuthAccessor object."""

    def test_initializer(self):
        """Test Initializer."""
        auth_id = self.aws_db_auth.id
        accessor = ProviderAuthDBAccessor(auth_id)
        self.assertTrue(accessor.does_db_entry_exist())
        self.assertEqual(int(auth_id), accessor.get_auth_id())

    def test_initializer_credentials(self):
        """Test Initializer with credentials."""
        credentials = self.ocp_provider.authentication.credentials
        accessor = ProviderAuthDBAccessor(credentials=credentials)
        self.assertTrue(accessor.does_db_entry_exist())

    def test_initializer_auth_id_and_credentials(self):
        """Test Initializer with auth_id and credentials."""
        auth_id = self.ocp_db_auth.id
        credentials = self.ocp_provider.authentication.credentials
        accessor = ProviderAuthDBAccessor(auth_id=auth_id, credentials=credentials)
        self.assertTrue(accessor.does_db_entry_exist())
        self.assertEqual(int(auth_id), accessor.get_auth_id())

    def test_initializer_no_args(self):
        """Test Initializer with no arguments."""
        accessor = ProviderAuthDBAccessor()
        self.assertFalse(accessor.does_db_entry_exist())

    def test_get_uuid(self):
        """Test uuid getter."""
        auth_id = self.aws_db_auth.id
        accessor = ProviderAuthDBAccessor(auth_id)
        self.assertEqual(self.aws_provider.authentication.uuid, accessor.get_uuid())

    def test_get_credentials(self):
        """Test provider name getter."""
        auth_id = self.aws_db_auth.id
        accessor = ProviderAuthDBAccessor(auth_id)
        self.assertEqual(self.aws_provider.authentication.credentials, accessor.get_credentials())
