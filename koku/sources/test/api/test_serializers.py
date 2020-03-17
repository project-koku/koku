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
from unittest.mock import Mock
from unittest.mock import patch

from faker import Faker
from model_bakery import baker
from rest_framework.serializers import ValidationError

from api.iam import models as iam_models
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.models import Sources
from api.provider.test import create_generic_provider
from providers.provider_access import ProviderAccessor
from sources.api import get_account_from_header
from sources.api import HEADER_X_RH_IDENTITY
from sources.api.serializers import AdminSourcesSerializer
from sources.api.serializers import SourcesSerializer
from sources.config import Config
from sources.storage import SourcesStorageError

fake = Faker()


class SourcesSerializerTests(IamTestCase):
    """Test Cases for the sources endpoint."""

    def setUp(self):
        """Set up tests."""
        super().setUp()
        customer = self._create_customer_data()
        self.User = baker.make(iam_models.User)
        self.Customer = iam_models.Customer.objects.get(schema_name=self.tenant.schema_name)

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

    def _create_source_and_provider(self, provider_type, source_id):
        """Create Provider."""
        _, provider = create_generic_provider(provider_type, self.headers)
        source = Sources.objects.get(source_id=source_id)
        source.source_uuid = provider.uuid
        authentication = {"credentials": provider.authentication.credentials}
        if authentication.get("credentials").get("provider_resource_name"):
            authentication["resource_name"] = authentication["credentials"]["provider_resource_name"]
        source.authentication = authentication
        billing_source = {"data_source": provider.billing_source.data_source}
        source.billing_source = billing_source
        source.save()
        return source

    @patch("api.provider.serializers.ProviderSerializer.get_request_info")
    @patch("sources.kafka_source_manager.KafkaSourceManager._create_context")
    def test_azure_source_update_missing_credential(self, mock_context, mock_request_info):
        """Test the updating azure source with invalid authentication."""
        mock_context.return_value = self.request_context, self.Customer, self.User
        mock_request_info.return_value = self.User, self.Customer
        source = self._create_source_and_provider(Provider.PROVIDER_AZURE, self.test_azure_source_id)
        source.authentication.get("credentials").pop("subscription_id")
        source.save()

        serializer = SourcesSerializer(context=self.request_context)
        validated_data = {"authentication": {"credentials": {"subscription_id": "subscription-uuid"}}}
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            instance = serializer.update(source, validated_data)
        self.assertEqual("subscription-uuid", instance.authentication.get("credentials").get("subscription_id"))
        for field in ("client_id", "tenant_id", "client_secret"):
            self.assertIn(field, instance.authentication.get("credentials").keys())

    def test_azure_source_update_wrong_type(self):
        """Test the updating azure source with wrong source type."""
        self.azure_obj.source_type = Provider.PROVIDER_AWS
        self.azure_obj.save()

        serializer = SourcesSerializer(context=self.request_context)
        validated_data = {"authentication": {"credentials": {"subscription_id": "subscription-uuid"}}}
        with self.assertRaises(SourcesStorageError):
            serializer.update(self.azure_obj, validated_data)

    @patch("api.provider.serializers.ProviderSerializer.get_request_info")
    @patch("sources.kafka_source_manager.KafkaSourceManager._create_context")
    def test_azure_source_billing_source_update(self, mock_context, mock_request_info):
        """Test the updating azure billing_source."""
        mock_context.return_value = self.request_context, self.Customer, self.User
        mock_request_info.return_value = self.User, self.Customer
        source = self._create_source_and_provider(Provider.PROVIDER_AZURE, self.test_azure_source_id)

        serializer = SourcesSerializer(context=self.request_context)
        test_resource_group = "TESTRG"
        test_storage_account = "testsa"
        validated_data = {
            "billing_source": {
                "data_source": {"resource_group": test_resource_group, "storage_account": test_storage_account}
            }
        }
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            instance = serializer.update(source, validated_data)
        self.assertIn("data_source", instance.billing_source.keys())
        self.assertEqual(test_resource_group, instance.billing_source.get("data_source").get("resource_group"))
        self.assertEqual(test_storage_account, instance.billing_source.get("data_source").get("storage_account"))

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

    @patch("api.provider.serializers.ProviderSerializer.get_request_info")
    @patch("sources.kafka_source_manager.KafkaSourceManager._create_context")
    def test_aws_source_billing_source_update(self, mock_context, mock_request_info):
        """Test the updating aws billing_source."""
        mock_context.return_value = self.request_context, self.Customer, self.User
        mock_request_info.return_value = self.User, self.Customer
        source = self._create_source_and_provider(Provider.PROVIDER_AWS, self.test_aws_source_id)

        serializer = SourcesSerializer(context=self.request_context)
        test_bucket = "some-new-bucket"
        validated_data = {"billing_source": {"bucket": test_bucket}}
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            instance = serializer.update(source, validated_data)
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

    def test_create_via_admin_serializer(self):
        """Test create source with admin serializer."""
        source_data = {
            "name": "test1",
            "source_type": "AWS",
            "authentication": {"resource_name": "arn:aws::foo:bar"},
            "billing_source": {"bucket": "/tmp/s3bucket"},
        }
        mock_request = Mock(headers={HEADER_X_RH_IDENTITY: Config.SOURCES_FAKE_HEADER})
        context = {"request": mock_request}
        serializer = AdminSourcesSerializer(data=source_data, context=context)
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()
                provider = Provider.objects.get(uuid=instance.koku_uuid)
                self.assertIsNotNone(provider)
                self.assertEqual(provider.name, instance.name)
                self.assertEqual(instance.source_uuid, instance.koku_uuid)
            else:
                self.fail("test_create_via_admin_serializer failed")

        source_data["name"] = "test2"
        source_data["authentication"]["resource_name"] = "arn:aws::foo:bar2"
        source_data["billing_source"]["bucket"] = "/tmp/mybucket"
        serializer = AdminSourcesSerializer(data=source_data, context=context)
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()
                provider = Provider.objects.get(uuid=instance.koku_uuid)
                self.assertIsNotNone(provider)
                self.assertEqual(provider.name, instance.name)
                self.assertEqual(instance.source_uuid, instance.koku_uuid)
            else:
                self.fail("test_create_via_admin_serializer failed")

    def test_create_via_admin_serializer_bad_source_type(self):
        """Raise error for bad source type on create."""
        source_data = {
            "name": "test",
            "source_type": "BAD",
            "authentication": {"resource_name": "arn:aws::foo:bar"},
            "billing_source": {"bucket": "/tmp/s3bucket"},
        }
        mock_request = Mock(headers={HEADER_X_RH_IDENTITY: Config.SOURCES_FAKE_HEADER})
        context = {"request": mock_request}
        serializer = AdminSourcesSerializer(data=source_data, context=context)
        with self.assertRaises(ValidationError):
            if serializer.is_valid(raise_exception=True):
                serializer.save()

    def test_negative_get_account_from_header(self):
        """Test flow with out header."""
        account = get_account_from_header(Mock(headers={}))
        self.assertIsNone(account)

        account = get_account_from_header(Mock(headers={HEADER_X_RH_IDENTITY: "badencoding&&&"}))
        self.assertIsNone(account)

    @patch("api.provider.serializers.ProviderSerializer.get_request_info")
    @patch("sources.kafka_source_manager.KafkaSourceManager._create_context")
    def test_provider_create(self, mock_context, mock_request_info):
        mock_context.return_value = self.request_context, self.Customer, self.User
        mock_request_info.return_value = self.User, self.Customer

        serializer = AdminSourcesSerializer(context=self.request_context)
        source = {
            "source_id": 10,
            "name": "ProviderAWS",
            "source_type": "AWS",
            "authentication": {"resource_name": "arn:aws:iam::111111111111:role/CostManagement"},
            "billing_source": {"bucket": "first-bucket"},
            "auth_header": self.request_context["request"].META,
            "account_id": "acct10001",
            "offset": 10,
        }
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            instance = serializer.create(source)
        self.assertEqual(instance.billing_source.get("bucket"), "first-bucket")

        serializer = SourcesSerializer(context=self.request_context)
        validated = {"billing_source": {"bucket": "second-bucket"}}
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            instance2 = serializer.update(instance, validated)
        self.assertEqual(instance2.billing_source.get("bucket"), "second-bucket")
