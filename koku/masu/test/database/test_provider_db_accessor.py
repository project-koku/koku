#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ProviderDBAccessor utility object."""
from unittest.mock import patch

from api.provider.models import Provider
from api.provider.models import ProviderInfrastructureMap
from masu.database.customer_db_accessor import CustomerDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external.date_accessor import DateAccessor
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
        auth_id = self.aws_db_auth.id
        with ProviderDBAccessor(auth_id=auth_id) as accessor:
            self.assertTrue(accessor.does_db_entry_exist())

    def test_initializer_provider_uuid_and_auth_id(self):
        """Test Initializer with provider uuid and authentication database id."""
        auth_id = self.aws_db_auth.id
        uuid = self.aws_provider_uuid
        with ProviderDBAccessor(provider_uuid=uuid, auth_id=auth_id) as accessor:
            self.assertTrue(accessor.does_db_entry_exist())

    def test_initializer_provider_uuid_and_auth_id_mismatch(self):
        """Test Initializer with provider uuid and authentication database id mismatch."""
        auth_id = self.ocp_db_auth.id
        uuid = self.aws_provider_uuid
        with ProviderDBAccessor(provider_uuid=uuid, auth_id=auth_id) as accessor:
            self.assertFalse(accessor.does_db_entry_exist())

    def test_initializer_no_args(self):
        """Test Initializer with no arguments."""
        with ProviderDBAccessor() as accessor:
            self.assertFalse(accessor.does_db_entry_exist())

    def test_get_uuid(self):
        """Test uuid getter."""
        uuid = self.aws_provider_uuid
        with ProviderDBAccessor(uuid) as accessor:
            self.assertEqual(uuid, accessor.get_uuid())

    def test_get_provider_name(self):
        """Test provider name getter."""
        uuid = self.aws_provider_uuid
        with ProviderDBAccessor(uuid) as accessor:
            self.assertEqual(accessor.get_provider_name(), self.aws_provider.name)

    def test_get_type(self):
        """Test provider type getter."""
        uuid = self.aws_provider_uuid
        with ProviderDBAccessor(uuid) as accessor:
            self.assertIn(accessor.get_type(), (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL))

    def test_get_credentials(self):
        """Test provider credentials getter."""
        uuid = self.aws_provider_uuid
        expected_creds_dict = self.aws_db_auth.credentials
        with ProviderDBAccessor(uuid) as accessor:
            self.assertEqual(expected_creds_dict, accessor.get_credentials())

    def test_get_data_source(self):
        """Test provider data_source getter."""
        uuid = self.aws_provider_uuid
        expected_data_source = self.aws_billing_source.data_source
        with ProviderDBAccessor(uuid) as accessor:
            self.assertEqual(expected_data_source, accessor.get_data_source())

    def test_get_data_source_no_data_source(self):
        """Test provider data_source getter."""
        uuid = self.unkown_test_provider_uuid
        with ProviderDBAccessor(uuid) as accessor:
            self.assertIsNone(accessor.get_data_source())

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

    def test_get_infrastructure_type_none_provider(self):
        """Test no failure when obtaining infrastructure when a provider doesn't exist."""
        with ProviderDBAccessor(self.unkown_test_provider_uuid) as accessor:
            self.assertIsNone(accessor.infrastructure)

    def test_set_infrastructure(self):
        """Test that infrastructure provider UUID is returned."""
        infrastructure_type = Provider.PROVIDER_AWS
        with ProviderDBAccessor(self.ocp_provider_uuid) as accessor:
            accessor.set_infrastructure(self.aws_provider_uuid, infrastructure_type)

        mapping = ProviderInfrastructureMap.objects.filter(
            infrastructure_provider_id=self.aws_provider_uuid, infrastructure_type=infrastructure_type
        ).first()

        mapping_on_provider = Provider.objects.filter(infrastructure=mapping).first()
        self.assertEqual(mapping.id, mapping_on_provider.infrastructure.id)

    def test_delete_ocp_infrastructure(self):
        """Test deleting an OCP infra type from the ProviderInfrastructureMap."""
        infrastructure_type = Provider.PROVIDER_OCP
        with ProviderDBAccessor(self.ocp_provider_uuid) as accessor:
            accessor.set_infrastructure(self.aws_provider_uuid, infrastructure_type)

        mapping = ProviderInfrastructureMap.objects.filter(
            infrastructure_provider_id=self.aws_provider_uuid, infrastructure_type=infrastructure_type
        ).first()

        mapping_on_provider = Provider.objects.filter(infrastructure=mapping).first()
        self.assertEqual(mapping.id, mapping_on_provider.infrastructure.id)

        with ProviderDBAccessor(self.ocp_provider_uuid) as accessor:
            accessor.delete_ocp_infra(self.aws_provider_uuid)

        infra_count = ProviderInfrastructureMap.objects.filter(
            infrastructure_provider_id=self.aws_provider_uuid, infrastructure_type=infrastructure_type
        ).count()
        self.assertEqual(infra_count, 0)

    @patch("api.provider.models.ProviderInfrastructureMap.delete")
    def test_delete_ocp_infrastructure_no_ocp_infras(self, mock_delete):
        """Test deleting an OCP infra type from the ProviderInfrastructureMap."""
        infrastructure_type = Provider.PROVIDER_OCP

        infra_count = ProviderInfrastructureMap.objects.filter(infrastructure_type=infrastructure_type).count()
        self.assertEqual(infra_count, 0)

        with ProviderDBAccessor(self.ocp_provider_uuid) as accessor:
            accessor.delete_ocp_infra(self.aws_provider_uuid)

        mock_delete.assert_not_called()

    def test_get_associated_openshift_providers(self):
        """Test that infrastructure provider UUID is returned."""
        infrastructure_type = Provider.PROVIDER_AWS_LOCAL
        with ProviderDBAccessor(self.ocp_on_aws_ocp_provider.uuid) as accessor:
            accessor.set_infrastructure(self.aws_provider_uuid, infrastructure_type)

        with ProviderDBAccessor(self.aws_provider_uuid) as accessor:
            providers = accessor.get_associated_openshift_providers()

        self.assertEqual(len(providers), 1)
        self.assertEqual(providers[0].uuid, self.ocp_on_aws_ocp_provider.uuid)

    def test_set_data_updated_timestamp(self):
        """Test that the data updated timestamp is updated."""
        now = DateAccessor().today_with_timezone("UTC")
        ProviderDBAccessor(self.aws_provider_uuid).set_data_updated_timestamp()
        self.assertGreater(ProviderDBAccessor(self.aws_provider_uuid).provider.data_updated_timestamp, now)

    def test_get_updated_timestamp(self):
        """Test that the data updated timestamp is updated."""
        now = DateAccessor().today_with_timezone("UTC")
        ProviderDBAccessor(self.aws_provider_uuid).set_data_updated_timestamp()
        get_timestamp = ProviderDBAccessor(self.aws_provider_uuid).get_data_updated_timestamp()
        self.assertGreater(get_timestamp, now)

    def test_get_updated_timestamp_no_provider(self):
        """Test that the data updated timestamp is updated."""
        get_timestamp = ProviderDBAccessor().get_data_updated_timestamp()
        self.assertEqual(get_timestamp, None)

    def test_set_additional_context(self):
        """Test that the additional context is updated."""
        context = {"new": "context"}
        ProviderDBAccessor(self.aws_provider_uuid).set_additional_context(context)
        self.assertDictEqual(ProviderDBAccessor(self.aws_provider_uuid).provider.additional_context, context)
