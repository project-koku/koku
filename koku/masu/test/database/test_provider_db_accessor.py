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
from api.provider.models import Provider, ProviderInfrastructureMap
from masu.database.customer_db_accessor import CustomerDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.test import MasuTestCase


class ProviderDBAccessorTest(MasuTestCase):
    """Test Cases for the ProviderDBAccessor object."""

    def test_initializer_provider_uuid(self):
        """Test Initializer with provider uuid."""
        uuid = self.aws_provider_uuid
        with ProviderDBAccessor(uuid) as accessor:
            self.assertTrue(accessor.does_db_entry_exist())

    def test_initializer_auth_id(self):
        """Test Initializer with authentication database id."""
        auth_id = self.aws_db_auth_id
        with ProviderDBAccessor(auth_id=auth_id) as accessor:
            self.assertTrue(accessor.does_db_entry_exist())

    def test_initializer_provider_uuid_and_auth_id(self):
        """Test Initializer with provider uuid and authentication database id."""
        auth_id = self.aws_db_auth_id
        uuid = self.aws_provider_uuid
        with ProviderDBAccessor(provider_uuid=uuid, auth_id=auth_id) as accessor:
            self.assertTrue(accessor.does_db_entry_exist())

    def test_initializer_provider_uuid_and_auth_id_mismatch(self):
        """Test Initializer with provider uuid and authentication database id mismatch."""
        auth_id = self.ocp_db_auth_id
        uuid = self.aws_provider_uuid
        with ProviderDBAccessor(provider_uuid=uuid, auth_id=auth_id) as accessor:
            self.assertFalse(accessor.does_db_entry_exist())

    def test_initializer_no_args(self):
        """Test Initializer with no arguments."""
        with ProviderDBAccessor() as accessor:
            self.assertTrue(accessor.does_db_entry_exist())

    def test_get_uuid(self):
        """Test uuid getter."""
        uuid = self.aws_provider_uuid
        with ProviderDBAccessor(uuid) as accessor:
            self.assertEqual(uuid, accessor.get_uuid())

    def test_get_provider_name(self):
        """Test provider name getter."""
        uuid = self.aws_provider_uuid
        with ProviderDBAccessor(uuid) as accessor:
            self.assertEqual('Test Provider', accessor.get_provider_name())

    def test_get_type(self):
        """Test provider type getter."""
        uuid = self.aws_provider_uuid
        with ProviderDBAccessor(uuid) as accessor:
            self.assertEqual(Provider.PROVIDER_AWS, accessor.get_type())

    def test_get_authentication(self):
        """Test provider authentication getter."""
        uuid = self.aws_provider_uuid
        expected_auth_string = self.aws_provider_resource_name
        with ProviderDBAccessor(uuid) as accessor:
            self.assertEqual(expected_auth_string, accessor.get_authentication())

    def test_get_billing_source(self):
        """Test provider billing_source getter."""
        uuid = self.aws_provider_uuid
        expected_billing_source = 'test-bucket'
        with ProviderDBAccessor(uuid) as accessor:
            self.assertEqual(expected_billing_source, accessor.get_billing_source())

    def test_get_customer_uuid(self):
        """Test provider billing_source getter."""
        expected_uuid = None
        with CustomerDBAccessor(self.customer.id) as customer_accessor:
            expected_uuid = customer_accessor.get_uuid()

        uuid = self.aws_provider_uuid
        with ProviderDBAccessor(uuid) as accessor:
            self.assertEqual(expected_uuid, accessor.get_customer_uuid())

    def test_get_customer_name(self):
        """Test provider customer getter."""
        uuid = self.aws_provider_uuid
        expected_customer_name = self.schema
        with ProviderDBAccessor(uuid) as accessor:
            self.assertEqual(expected_customer_name, accessor.get_customer_name())

    def test_get_schema(self):
        """Test provider schema getter."""
        uuid = self.aws_provider_uuid
        expected_schema = self.schema
        with ProviderDBAccessor(uuid) as accessor:
            self.assertEqual(expected_schema, accessor.get_schema())

    def test_get_setup_complete(self):
        """Test provider setup_complete getter."""
        uuid = self.aws_provider_uuid
        with ProviderDBAccessor(uuid) as accessor:
            self.assertEqual(False, accessor.get_setup_complete())

    def test_setup_complete(self):
        """Test provider setup_complete method."""
        uuid = self.aws_provider_uuid
        with ProviderDBAccessor(uuid) as accessor:
            accessor.setup_complete()
            self.assertEqual(True, accessor.get_setup_complete())

    def test_get_infrastructure_type(self):
        """Test that infrastructure type is returned."""
        infrastructure_type = Provider.PROVIDER_AWS
        with ProviderDBAccessor(self.ocp_provider_uuid) as accessor:
            accessor.set_infrastructure(self.aws_provider_uuid, infrastructure_type)
            self.assertEqual(accessor.get_infrastructure_type(), infrastructure_type)

    def test_get_infrastructure_provider_uuid(self):
        """Test that infrastructure provider UUID is returned."""
        infrastructure_type = Provider.PROVIDER_AWS
        with ProviderDBAccessor(self.ocp_provider_uuid) as accessor:
            accessor.set_infrastructure(self.aws_provider_uuid, infrastructure_type)
            self.assertEqual(accessor.get_infrastructure_provider_uuid(), self.aws_provider_uuid)

    def test_set_infrastructure(self):
        """Test that infrastructure provider UUID is returned."""
        infrastructure_type = Provider.PROVIDER_AWS
        with ProviderDBAccessor(self.ocp_provider_uuid) as accessor:
            accessor.set_infrastructure(self.aws_provider_uuid, infrastructure_type)

        mapping = ProviderInfrastructureMap.objects.filter(
            infrastructure_provider_id=self.aws_provider_uuid,
            infrastructure_type=infrastructure_type,
        ).first()

        mapping_on_provider = Provider.objects.filter(infrastructure=mapping).first()
        self.assertEqual(mapping.id, mapping_on_provider.infrastructure.id)

    def test_get_associated_openshift_providers(self):
        """Test that infrastructure provider UUID is returned."""
        infrastructure_type = Provider.PROVIDER_AWS
        with ProviderDBAccessor(self.ocp_provider_uuid) as accessor:
            accessor.set_infrastructure(self.aws_provider_uuid, infrastructure_type)

        with ProviderDBAccessor(self.aws_provider_uuid) as accessor:
            providers = accessor.get_associated_openshift_providers()

        self.assertEqual(len(providers), 1)
        self.assertEqual(str(providers[0].uuid), self.ocp_provider_uuid)
