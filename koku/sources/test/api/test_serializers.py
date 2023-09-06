#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
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
from api.provider.provider_builder import ProviderBuilder
from providers.provider_access import ProviderAccessor
from providers.provider_errors import SkipStatusPush
from sources.api import get_param_from_header
from sources.api import HEADER_X_RH_IDENTITY
from sources.api.serializers import AdminSourcesSerializer
from sources.config import Config

fake = Faker()


class MockSourcesClient:
    def __init__(self, address):
        self._url = address


class AdminSourcesSerializerTests(IamTestCase):
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

    def test_create_via_admin_serializer(self):
        """Test create source with admin serializer."""
        source_data = {
            "name": "test1",
            "source_type": "AWS",
            "authentication": {"credentials": {"role_arn": "arn:aws::foo:bar"}},
            "billing_source": {"data_source": {"bucket": "/tmp/s3bucket"}},
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
        source_data["authentication"] = {"credentials": {"role_arn": "arn:aws::foo:bar2"}}
        source_data["billing_source"] = {"data_source": {"bucket": "/tmp/mybucket"}}
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
            "authentication": {"credentials": {"role_arn": "arn:aws::foo:bar"}},
            "billing_source": {"data_source": {"bucket": "/tmp/s3bucket"}},
        }
        mock_request = Mock(headers={HEADER_X_RH_IDENTITY: Config.SOURCES_FAKE_HEADER})
        context = {"request": mock_request}
        serializer = AdminSourcesSerializer(data=source_data, context=context)
        with self.assertRaises(ValidationError):
            if serializer.is_valid(raise_exception=True):
                serializer.save()

    def test_negative_get_param_from_header(self):
        """Test flow with out header."""
        account = get_param_from_header(Mock(headers={}), "account_number")
        self.assertIsNone(account)

        account = get_param_from_header(Mock(headers={HEADER_X_RH_IDENTITY: "badencoding&&&"}), "account_number")
        self.assertIsNone(account)

    @patch("api.provider.serializers.ProviderSerializer.get_request_info")
    @patch("sources.api.serializers.get_auth_header", return_value=Config.SOURCES_FAKE_HEADER)
    def test_provider_create(self, mock_header, mock_request_info):
        mock_request_info.return_value = self.User, self.Customer

        serializer = AdminSourcesSerializer(context=self.request_context)
        source = {
            "source_id": 10,
            "name": "ProviderAWS",
            "source_type": "AWS",
            "authentication": {"credentials": {"role_arn": "arn:aws:iam::111111111111:role/CostManagement"}},
            "billing_source": {"data_source": {"bucket": "first-bucket"}},
            "auth_header": Config.SOURCES_FAKE_HEADER,
            "account_id": "org1234567",
            "org_id": "org1234567",
            "offset": 10,
        }
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            instance = serializer.create(source)
        self.assertEqual(instance.billing_source.get("data_source", {}).get("bucket"), "first-bucket")

    @patch("api.provider.serializers.ProviderSerializer.get_request_info")
    @patch("sources.api.serializers.get_auth_header", return_value=Config.SOURCES_FAKE_HEADER)
    def test_gcp_admin_add_table_not_ready(self, mock_header, mock_request_info):
        """Test a GCP Admin Source add where the billing table is not ready."""
        mock_request_info.return_value = self.User, self.Customer

        serializer = AdminSourcesSerializer(context=self.request_context)
        with self.assertRaises(ValidationError):
            with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
                with patch.object(ProviderBuilder, "create_provider_from_source", side_effect=SkipStatusPush):
                    serializer.create(
                        {
                            "source_id": 10,
                            "name": "ProviderGCP",
                            "source_type": "GCP",
                            "authentication": {"credentials": {"project_id": "test-project"}},
                            "billing_source": {"data_source": {"dataset": "first-dataset"}},
                            "auth_header": Config.SOURCES_FAKE_HEADER,
                            "account_id": "org1234567",
                            "org_id": "org1234567",
                            "offset": 10,
                        }
                    )
