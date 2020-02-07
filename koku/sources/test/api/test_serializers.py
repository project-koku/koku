#
# Copyright 2019 Red Hat, Inc.
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
"""Test the sources serializer."""
from faker import Faker

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.models import Sources
from sources.api.serializers import SourcesSerializer
from sources.storage import SourcesStorageError

fake = Faker()


class SourcesSerializerTests(IamTestCase):
    """Test Cases for the sources endpoint."""

    def setUp(self):
        """Set up tests."""
        super().setUp()
        customer = self._create_customer_data()

        self.azure_name = "Test Azure Source"
        azure_user_data = self._create_user_data()
        self.azure_request_context = self._create_request_context(
            customer, azure_user_data, create_customer=True, is_admin=False
        )
        self.test_azure_source_id = 1

        self.azure_obj = Sources(
            source_id=self.test_azure_source_id,
            auth_header=self.azure_request_context["request"].META,
            account_id=customer.get("account_id"),
            offset=1,
            source_type=Provider.PROVIDER_AZURE,
            name=self.azure_name,
            authentication={
                "credentials": {"client_id": "test_client", "tenant_id": "test_tenant", "client_secret": "test_secret"}
            },
        )
        self.azure_obj.save()

        self.aws_name = "Test AWS Source"
        aws_user_data = self._create_user_data()
        self.aws_request_context = self._create_request_context(
            customer, aws_user_data, create_customer=True, is_admin=False
        )
        self.test_aws_source_id = 2

        self.aws_obj = Sources(
            source_id=self.test_aws_source_id,
            auth_header=self.aws_request_context["request"].META,
            account_id=customer.get("account_id"),
            offset=2,
            source_type=Provider.PROVIDER_AWS,
            name=self.aws_name,
        )
        self.aws_obj.save()

    def test_azure_source_authentication_update(self):
        """Test the updating azure subscription id."""
        serializer = SourcesSerializer(context=self.request_context)
        validated_data = {"authentication": {"credentials": {"subscription_id": "subscription-uuid"}}}
        instance = serializer.update(self.azure_obj, validated_data)
        self.assertIn("credentials", instance.authentication.keys())
        self.assertIn("client_id", instance.authentication.get("credentials").keys())
        self.assertIn("tenant_id", instance.authentication.get("credentials").keys())
        self.assertIn("subscription_id", instance.authentication.get("credentials").keys())
        self.assertEqual("subscription-uuid", instance.authentication.get("credentials").get("subscription_id"))

    def test_azure_source_update_with_koku_uuid(self):
        """Test the updating azure subscription id with a koku_uuid."""
        self.azure_obj.koku_uuid = fake.uuid4()
        self.azure_obj.pending_update = False
        self.azure_obj.save()

        serializer = SourcesSerializer(context=self.request_context)
        validated_data = {"authentication": {"credentials": {"subscription_id": "subscription-uuid"}}}
        instance = serializer.update(self.azure_obj, validated_data)
        self.assertTrue(instance.pending_update)

    def test_azure_source_update_missing_credential(self):
        """Test the updating azure source with invalid authentication."""
        self.azure_obj.authentication = {}
        self.azure_obj.save()

        serializer = SourcesSerializer(context=self.request_context)
        validated_data = {"authentication": {"credentials": {"subscription_id": "subscription-uuid"}}}
        instance = serializer.update(self.azure_obj, validated_data)
        self.assertEqual("subscription-uuid", instance.authentication.get("credentials").get("subscription_id"))
        for field in ("client_id", "tenant_id", "client_secret"):
            self.assertNotIn(field, instance.authentication.get("credentials").keys())

    def test_azure_source_update_wrong_type(self):
        """Test the updating azure source with wrong source type."""
        self.azure_obj.source_type = Provider.PROVIDER_AWS
        self.azure_obj.save()

        serializer = SourcesSerializer(context=self.request_context)
        validated_data = {"authentication": {"credentials": {"subscription_id": "subscription-uuid"}}}
        with self.assertRaises(SourcesStorageError):
            serializer.update(self.azure_obj, validated_data)

    def test_azure_source_billing_source_update(self):
        """Test the updating azure billing_source."""
        serializer = SourcesSerializer(context=self.request_context)
        test_resource_group = "TESTRG"
        test_storage_account = "testsa"
        validated_data = {
            "billing_source": {
                "data_source": {"resource_group": test_resource_group, "storage_account": test_storage_account}
            }
        }
        instance = serializer.update(self.azure_obj, validated_data)
        self.assertIn("data_source", instance.billing_source.keys())
        self.assertEqual(test_resource_group, instance.billing_source.get("data_source").get("resource_group"))
        self.assertEqual(test_storage_account, instance.billing_source.get("data_source").get("storage_account"))

    def test_azure_source_billing_source_update_with_koku_uuid(self):
        """Test the updating azure billing_source with koku_uuid."""
        self.azure_obj.koku_uuid = fake.uuid4()
        self.azure_obj.pending_update = False
        self.azure_obj.save()

        serializer = SourcesSerializer(context=self.request_context)
        test_resource_group = "TESTRG"
        test_storage_account = "testsa"
        validated_data = {
            "billing_source": {
                "data_source": {"resource_group": test_resource_group, "storage_account": test_storage_account}
            }
        }
        instance = serializer.update(self.azure_obj, validated_data)
        self.assertTrue(instance.pending_update)

    def test_azure_source_billing_source_update_missing_data_source(self):
        """Test the updating azure billing_source with missing data_source."""
        serializer = SourcesSerializer(context=self.request_context)
        validated_data = {"billing_source": {"wrong": {}}}
        with self.assertRaises(SourcesStorageError):
            serializer.update(self.azure_obj, validated_data)

    def test_azure_source_billing_source_update_missing_resource_group(self):
        """Test the updating azure billing_source with missing resource group."""
        serializer = SourcesSerializer(context=self.request_context)
        test_storage_account = "testsa"
        validated_data = {"billing_source": {"data_source": {"storage_account": test_storage_account}}}
        with self.assertRaises(SourcesStorageError):
            serializer.update(self.azure_obj, validated_data)

    def test_azure_source_billing_source_update_missing_storage_account(self):
        """Test the updating azure billing_source with missing storage account."""
        serializer = SourcesSerializer(context=self.request_context)
        test_resource_group = "TESTRG"
        validated_data = {"billing_source": {"data_source": {"resource_group": test_resource_group}}}
        with self.assertRaises(SourcesStorageError):
            serializer.update(self.azure_obj, validated_data)

    def test_aws_source_billing_source_update(self):
        """Test the updating aws billing_source."""
        serializer = SourcesSerializer(context=self.request_context)
        test_bucket = "test-bucket"
        validated_data = {"billing_source": {"bucket": test_bucket}}
        instance = serializer.update(self.aws_obj, validated_data)
        self.assertIn("bucket", instance.billing_source.keys())
        self.assertEqual(test_bucket, instance.billing_source.get("bucket"))

    def test_aws_source_billing_source_update_missing_bucket(self):
        """Test the updating aws billing_source."""
        serializer = SourcesSerializer(context=self.request_context)
        test_bucket = None
        validated_data = {"billing_source": {"bucket": test_bucket}}
        with self.assertRaises(SourcesStorageError):
            serializer.update(self.aws_obj, validated_data)

    def test_ocp_source_billing_source_update(self):
        """Test the updating billing_source for invalid OCP source."""
        self.aws_obj.instance_type = Provider.PROVIDER_OCP
        self.aws_obj.save()
        test_bucket = "test-bucket"
        serializer = SourcesSerializer(context=self.request_context)
        test_bucket = None
        validated_data = {"billing_source": {"bucket": test_bucket}}
        with self.assertRaises(SourcesStorageError):
            serializer.update(self.aws_obj, validated_data)
