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
"""Test the Provider serializers."""
import copy
import random
import uuid
from itertools import permutations
from unittest.mock import patch

from faker import Faker
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from api.iam.serializers import create_schema_name
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.models import Sources
from api.provider.serializers import AdminProviderSerializer
from api.provider.serializers import ProviderSerializer
from api.provider.serializers import REPORT_PREFIX_MAX_LENGTH
from providers.provider_access import ProviderAccessor
from providers.provider_errors import ProviderErrors

FAKE = Faker()


class ProviderSerializerTest(IamTestCase):
    """Tests for the customer serializer."""

    def setUp(self):
        """Create test case objects."""
        super().setUp()

        self.generic_providers = {
            Provider.PROVIDER_OCP: {
                "name": "test_provider",
                "type": Provider.PROVIDER_OCP.lower(),
                "authentication": {"credentials": {"cluster_id": "my-ocp-cluster-1"}},
                "billing_source": {},
            },
            Provider.PROVIDER_AWS: {
                "name": "test_provider",
                "type": Provider.PROVIDER_AWS.lower(),
                "authentication": {"credentials": {"role_arn": "arn:aws:s3:::my_s3_bucket"}},
                "billing_source": {"data_source": {"bucket": "my_s3_bucket"}},
            },
            Provider.PROVIDER_AZURE: {
                "name": "test_provider",
                "type": Provider.PROVIDER_AZURE.lower(),
                "authentication": {
                    "credentials": {
                        "subscription_id": "12345678-1234-5678-1234-567812345678",
                        "tenant_id": "12345678-1234-5678-1234-567812345678",
                        "client_id": "12345678-1234-5678-1234-567812345678",
                        "client_secret": "12345",
                    }
                },
                "billing_source": {"data_source": {"resource_group": {}, "storage_account": {}}},
            },
        }

    def test_create_all_providers(self):
        """Tests that adding all unique providers together is successful."""
        list_of_uuids = []
        initial_date_updated = self.customer.date_updated
        self.assertIsNotNone(initial_date_updated)
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            serializer = ProviderSerializer(
                data=self.generic_providers[Provider.PROVIDER_AZURE], context=self.request_context
            )
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()
            schema_name = serializer.data["customer"].get("schema_name")
            self.assertIsInstance(instance.uuid, uuid.UUID)
            self.assertIsNone(schema_name)
            self.assertFalse("schema_name" in serializer.data["customer"])
            list_of_uuids.append(instance.uuid)
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            serializer = ProviderSerializer(
                data=self.generic_providers[Provider.PROVIDER_AWS], context=self.request_context
            )
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()
            schema_name = serializer.data["customer"].get("schema_name")
            self.assertIsInstance(instance.uuid, uuid.UUID)
            self.assertIsNone(schema_name)
            self.assertFalse("schema_name" in serializer.data["customer"])
            list_of_uuids.append(instance.uuid)
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            serializer = ProviderSerializer(
                data=self.generic_providers[Provider.PROVIDER_OCP], context=self.request_context
            )
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()
            schema_name = serializer.data["customer"].get("schema_name")
            self.assertIsInstance(instance.uuid, uuid.UUID)
            self.assertIsNone(schema_name)
            self.assertFalse("schema_name" in serializer.data["customer"])
            list_of_uuids.append(instance.uuid)

        for a, b in permutations(list_of_uuids, 2):
            self.assertNotEqual(a, b)

        self.assertGreater(self.customer.date_updated, initial_date_updated)

    def test_create_provider_fails_user(self):
        """Test creating a provider fails with no user."""
        provider = {
            "name": "test_provider",
            "type": Provider.PROVIDER_AWS.lower(),
            "authentication": {"credentials": {"role_arn": "arn:aws:s3:::my_s3_bucket"}},
            "billing_source": {"data_source": {"bucket": "my_s3_bucket"}},
        }
        serializer = ProviderSerializer(data=provider)
        if serializer.is_valid(raise_exception=True):
            with self.assertRaises(serializers.ValidationError):
                serializer.save()

    def test_create_provider_fails_customer(self):
        """Test creating a provider where customer is not found for user."""
        provider = {
            "name": "test_provider",
            "type": Provider.PROVIDER_AWS.lower(),
            "authentication": {"credentials": {"role_arn": "arn:aws:s3:::my_s3_bucket"}},
            "billing_source": {"data_source": {"bucket": "my_s3_bucket"}},
        }
        user_data = self._create_user_data()
        alt_request_context = self._create_request_context(
            self.create_mock_customer_data(), user_data, create_tenant=True
        )
        request = alt_request_context["request"]
        request.user.customer = None
        serializer = ProviderSerializer(data=provider, context=alt_request_context)
        if serializer.is_valid(raise_exception=True):
            with self.assertRaises(serializers.ValidationError):
                serializer.save()

    def test_create_aws_provider(self):
        """Test creating a provider."""
        iam_arn = "arn:aws:s3:::my_s3_bucket"
        bucket_name = "my_s3_bucket"
        provider = {
            "name": "test_provider",
            "type": Provider.PROVIDER_AWS.lower(),
            "authentication": {"credentials": {"role_arn": iam_arn}},
            "billing_source": {"data_source": {"bucket": bucket_name}},
        }
        instance = None

        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            serializer = ProviderSerializer(data=provider, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()

        schema_name = serializer.data["customer"].get("schema_name")
        self.assertIsInstance(instance.uuid, uuid.UUID)
        self.assertTrue(instance.active)
        self.assertIsNone(schema_name)
        self.assertFalse("schema_name" in serializer.data["customer"])

    def test_create_ocp_provider(self):
        """Test creating an OCP provider."""
        cluster_id = "my-ocp-cluster-1"
        provider = {
            "name": "test_provider",
            "type": Provider.PROVIDER_OCP.lower(),
            "authentication": {"credentials": {"cluster_id": cluster_id}},
            "billing_source": {},
        }

        instance = None
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            serializer = ProviderSerializer(data=provider, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()

        schema_name = serializer.data["customer"].get("schema_name")
        self.assertIsInstance(instance.uuid, uuid.UUID)
        self.assertTrue(instance.active)
        self.assertIsNone(schema_name)
        self.assertFalse("schema_name" in serializer.data["customer"])

    def test_create_ocp_source_with_existing_provider(self):
        """Test creating an OCP Source when the provider already exists."""
        cluster_id = "my-ocp-cluster-1"
        provider = {
            "name": "test_provider",
            "type": Provider.PROVIDER_OCP.lower(),
            "authentication": {"credentials": {"cluster_id": cluster_id}},
            "billing_source": {},
        }

        instance = None
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            serializer = ProviderSerializer(data=provider, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()

        schema_name = serializer.data["customer"].get("schema_name")
        self.assertIsInstance(instance.uuid, uuid.UUID)
        self.assertTrue(instance.active)
        self.assertIsNone(schema_name)
        self.assertFalse("schema_name" in serializer.data["customer"])

        # Add Source without provider uuid
        sources = Sources.objects.create(
            source_id=1, auth_header="testheader", offset=1, authentication={"cluster_id": cluster_id}
        )
        sources.save()
        # Verify ValidationError is raised when another source is added with an existing
        # provider.
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            serializer = ProviderSerializer(data=provider, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                with self.assertRaises(serializers.ValidationError):
                    serializer.save()

    def test_create_provider_with_credentials_and_data_source(self):
        """Test creating a provider with data_source field instead of bucket."""
        provider = {
            "name": "test_provider",
            "type": Provider.PROVIDER_AWS.lower(),
            "authentication": {"credentials": {"role_arn": "four"}},
            "billing_source": {"data_source": {"bucket": "bar"}},
        }
        instance = None

        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            serializer = ProviderSerializer(data=provider, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()

        schema_name = serializer.data["customer"].get("schema_name")
        self.assertIsInstance(instance.uuid, uuid.UUID)
        self.assertTrue(instance.active)
        self.assertIsNone(schema_name)
        self.assertFalse("schema_name" in serializer.data["customer"])

    def test_create_provider_with_credentials_and_role_arn(self):
        """Test creating a provider with credentials and role_arn fields should fail."""
        iam_arn = "arn:aws:s3:::my_s3_bucket"
        provider = {
            "name": "test_provider",
            "type": Provider.PROVIDER_AWS.lower(),
            "authentication": {"credentials": {"role_arn": "four"}, "role_arn": iam_arn},
            "billing_source": {"data_source": {"bucket": "bar"}},
        }
        user_data = self._create_user_data()
        alt_request_context = self._create_request_context(
            self.create_mock_customer_data(), user_data, create_tenant=True
        )
        request = alt_request_context["request"]
        request.user.customer = None
        serializer = ProviderSerializer(data=provider, context=alt_request_context)
        if serializer.is_valid(raise_exception=True):
            with self.assertRaises(serializers.ValidationError):
                serializer.save()

    def test_create_provider_with_bucket_and_data_source(self):
        """Test creating a provider with data_source and bucket fields should fail."""
        bucket_name = "my_s3_bucket"
        provider = {
            "name": "test_provider",
            "type": Provider.PROVIDER_AWS.lower(),
            "authentication": {"credentials": {"role_arn": "four"}},
            "billing_source": {"data_source": {"bucket": "bar"}, "bucket": bucket_name},
        }
        user_data = self._create_user_data()
        alt_request_context = self._create_request_context(
            self.create_mock_customer_data(), user_data, create_tenant=True
        )
        request = alt_request_context["request"]
        request.user.customer = None
        serializer = ProviderSerializer(data=provider, context=alt_request_context)
        if serializer.is_valid(raise_exception=True):
            with self.assertRaises(serializers.ValidationError):
                serializer.save()

    def test_create_provider_two_providers_shared_billing_record(self):
        """Test that the same blank billing entry is used for all OCP providers."""
        cluster_id = "my-ocp-cluster-1"
        provider = {
            "name": "test_provider_one",
            "type": Provider.PROVIDER_OCP.lower(),
            "authentication": {"credentials": {"cluster_id": cluster_id}},
            "billing_source": {},
        }

        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            serializer = ProviderSerializer(data=provider, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                provider_one = serializer.save()

        cluster_id = "my-ocp-cluster-2"
        provider["name"] = "test_provider_two"
        provider["authentication"] = {"credentials": {"cluster_id": cluster_id}}
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            serializer = ProviderSerializer(data=provider, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                provider_two = serializer.save()

        self.assertEqual(provider_one.billing_source_id, provider_two.billing_source_id)

    def test_missing_creds_parameters_exception(self):
        """Test that ValidationError is raised when there are missing parameters."""
        fields = ["subscription_id", "tenant_id", "client_id", "client_secret"]
        credentials = {
            "subscription_id": FAKE.uuid4(),
            "tenant_id": FAKE.uuid4(),
            "client_id": FAKE.uuid4(),
            "client_secret": FAKE.word(),
        }
        source_name = {"resource_group": FAKE.word(), "storage_account": FAKE.word()}
        del credentials[random.choice(fields)]

        provider = {
            "name": FAKE.word(),
            "type": Provider.PROVIDER_AZURE.lower(),
            "authentication": {"credentials": credentials},
            "billing_source": {"data_source": source_name},
        }

        with self.assertRaises(ValidationError):
            serializer = ProviderSerializer(data=provider, context=self.request_context)
            serializer.is_valid(raise_exception=True)

    def test_missing_source_parameters_exception(self):
        """Test that ValidationError is raised when there are missing parameters."""
        fields = ["resource_group", "storage_account"]
        credentials = {
            "subscription_id": FAKE.uuid4(),
            "tenant_id": FAKE.uuid4(),
            "client_id": FAKE.uuid4(),
            "client_secret": FAKE.word(),
        }
        source_name = {"resource_group": FAKE.word(), "storage_account": FAKE.word()}
        del source_name[random.choice(fields)]

        provider = {
            "name": FAKE.word(),
            "type": Provider.PROVIDER_AZURE.lower(),
            "authentication": credentials,
            "billing_source": {"data_source": source_name},
        }

        with self.assertRaises(ValidationError):
            serializer = ProviderSerializer(data=provider, context=self.request_context)
            serializer.is_valid(raise_exception=True)

    def test_create_gcp_provider(self):
        """Test that the same blank billing entry is used for all OCP providers."""
        provider = {
            "name": "test_provider_one",
            "type": Provider.PROVIDER_GCP.lower(),
            "authentication": {"credentials": {"project_id": "gcp_project"}},
            "billing_source": {
                "data_source": {"dataset": "test_dataset", "table_id": "test_table_id", "report_prefix": "precious"}
            },
        }
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            serializer = ProviderSerializer(data=provider, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()

        schema_name = serializer.data["customer"].get("schema_name")
        self.assertIsInstance(instance.uuid, uuid.UUID)
        self.assertTrue(instance.active)
        self.assertIsNone(schema_name)
        self.assertFalse("schema_name" in serializer.data["customer"])

    def test_update_with_duplication_error(self):
        provider = self.generic_providers[Provider.PROVIDER_AWS]
        provider2 = copy.deepcopy(provider)
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            serializer = ProviderSerializer(data=provider, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                serializer.save()  # add first provider
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            provider2["billing_source"] = {"data_source": {"bucket": "my_new_bucket"}}
            serializer = ProviderSerializer(data=provider2, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                serializer.save()  # add second provider
            serializer.validated_data["billing_source"] = provider.get("billing_source")
            if serializer.is_valid(raise_exception=True):
                with self.assertRaises(ValidationError) as excCtx:
                    serializer.update(serializer.instance, serializer.validated_data)  # try to make second match first

            validationErr = excCtx.exception.detail[ProviderErrors.DUPLICATE_AUTH][0]
            self.assertTrue("Cost management does not allow duplicate accounts" in str(validationErr))

    def test_error_providers_with_same_auth_or_billing_source(self):
        """Test that the errors are wrapped correctly."""
        provider = self.generic_providers[Provider.PROVIDER_OCP]
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            serializer = ProviderSerializer(data=provider, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
            with self.assertRaises(ValidationError) as excCtx:
                serializer = ProviderSerializer(data=provider, context=self.request_context)
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

            validationErr = excCtx.exception.detail[ProviderErrors.DUPLICATE_AUTH][0]
            self.assertTrue("Cost management does not allow duplicate accounts" in str(validationErr))

    def test_error_update_provider_with_used_auth_or_billing_source(self):
        p1 = {
            "name": "test_provider_1",
            "type": Provider.PROVIDER_OCP.lower(),
            "authentication": {"credentials": {"cluster_id": "my-ocp-cluster-1"}},
            "billing_source": {},
        }
        p2 = {
            "name": "test_provider_2",
            "type": Provider.PROVIDER_OCP.lower(),
            "authentication": {"credentials": {"cluster_id": "my-ocp-cluster-2"}},
            "billing_source": {},
        }
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            serializer = ProviderSerializer(data=p1, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
            serializer = ProviderSerializer(data=p2, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()
                d = {
                    "name": "test_provider_2",
                    "type": Provider.PROVIDER_OCP.lower(),
                    "authentication": {"credentials": {"cluster_id": "my-ocp-cluster-1"}},
                    "billing_source": {},
                }
                with self.assertRaises(ValidationError) as excCtx:
                    serializer = ProviderSerializer(instance, data=d, context=self.request_context)
                    if serializer.is_valid(raise_exception=True):
                        serializer.save()
                validationErr = excCtx.exception.detail[ProviderErrors.DUPLICATE_AUTH][0]
                self.assertTrue("Cost management does not allow duplicate accounts" in str(validationErr))

    def test_create_gcp_provider_validate_no_data_source_bucket(self):
        """Test the data_source.bucket validation for GCP provider."""
        provider = {
            "name": "test_provider_val_data_source",
            "type": Provider.PROVIDER_GCP.lower(),
            "authentication": {"credentials": {"project_id": "gcp_project"}},
            "billing_source": {"data_source": {"potato": ""}},
        }

        with self.assertRaises(ValidationError) as e:
            serializer = ProviderSerializer(data=provider, context=self.request_context)
            serializer.is_valid(raise_exception=True)

        self.assertEqual(e.exception.status_code, 400)
        self.assertEqual(
            str(e.exception.detail["billing_source"]["data_source"]["provider.data_source"][0]),
            "One or more required fields is invalid/missing. Required fields are ['dataset', 'table_id']",
        )

    def test_create_gcp_provider_validate_report_prefix_too_long(self):
        """Test the data_source.report_prefix validation for GCP provider."""
        provider = {
            "name": "test_provider_val_data_source",
            "type": Provider.PROVIDER_GCP.lower(),
            "authentication": {"credentials": {"project_id": "gcp_project"}},
            "billing_source": {
                "data_source": {
                    "dataset": "test_dataset",
                    "table_id": "test_table_id",
                    "report_prefix": "an-unnecessarily-long-prefix-that-is-here-simply-for-the-purpose-of"
                    "testing-the-custom-validator-the-checks-for-too-long-of-a-report_prefix",
                }
            },
        }

        with self.assertRaises(ValidationError) as e:
            serializer = ProviderSerializer(data=provider, context=self.request_context)
            serializer.is_valid(raise_exception=True)

        self.assertEqual(e.exception.status_code, 400)
        self.assertEqual(
            str(e.exception.detail["billing_source"]["data_source"]["data_source.report_prefix"][0]),
            f"Ensure this field has no more than {REPORT_PREFIX_MAX_LENGTH} characters.",
        )

    def test_create_provider_invalid_type(self):
        """Test that an invalid provider type is not validated."""
        iam_arn = "arn:aws:s3:::my_s3_bucket"
        bucket_name = "my_s3_bucket"
        provider = {
            "name": "test_provider",
            "type": "Bad",
            "authentication": {"credentials": {"role_arn": iam_arn}},
            "billing_source": {"data_source": {"bucket": bucket_name}},
        }

        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            with self.assertRaises(ValidationError):
                serializer = ProviderSerializer(data=provider, context=self.request_context)
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_create_same_provider_different_customers(self):
        """Test that the same provider can be created for 2 different customers."""
        user_data = self._create_user_data()
        alt_request_context = self._create_request_context(
            self.create_mock_customer_data(), user_data, create_tenant=True
        )
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            serializer = ProviderSerializer(
                data=self.generic_providers[Provider.PROVIDER_AZURE], context=self.request_context
            )
            if serializer.is_valid(raise_exception=True):
                instance1 = serializer.save()

        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            serializer = ProviderSerializer(
                data=self.generic_providers[Provider.PROVIDER_AZURE], context=alt_request_context
            )
            if serializer.is_valid(raise_exception=True):
                instance2 = serializer.save()

        self.assertNotEqual(instance1.uuid, instance2.uuid)
        self.assertEqual(instance1.billing_source_id, instance2.billing_source_id)
        self.assertEqual(instance1.authentication_id, instance2.authentication_id)

    def test_create_provider_for_demo_account(self):
        """Test creating a provider for a demo account."""
        provider = {
            "name": "test_provider",
            "type": Provider.PROVIDER_AWS.lower(),
            "authentication": {"credentials": {"role_arn": "four"}},
            "billing_source": {"data_source": {"bucket": "bar"}},
        }
        instance = None

        account_id = self.customer_data.get("account_id")
        with self.settings(DEMO_ACCOUNTS={account_id: {}}):
            with patch.object(ProviderAccessor, "cost_usage_source_ready") as mock_method:
                serializer = ProviderSerializer(data=provider, context=self.request_context)
                if serializer.is_valid(raise_exception=True):
                    instance = serializer.save()
                    mock_method.assert_not_called()

        schema_name = serializer.data["customer"].get("schema_name")
        self.assertIsInstance(instance.uuid, uuid.UUID)
        self.assertTrue(instance.active)
        self.assertIsNone(schema_name)
        self.assertFalse("schema_name" in serializer.data["customer"])


class AdminProviderSerializerTest(IamTestCase):
    """Tests for the admin customer serializer."""

    def setUp(self):
        """Create test case objects."""
        super().setUp()

    def test_schema_name_present_on_customer(self):
        """Test that schema_name is returned on customer."""
        iam_arn = "arn:aws:s3:::my_s3_bucket"
        bucket_name = "my_s3_bucket"
        provider = {
            "name": "test_provider",
            "type": Provider.PROVIDER_AWS.lower(),
            "authentication": {"credentials": {"role_arn": iam_arn}},
            "billing_source": {"data_source": {"bucket": bucket_name}},
        }

        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            serializer = AdminProviderSerializer(data=provider, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                serializer.save()

        account = self.customer.account_id
        expected_schema_name = create_schema_name(account)
        schema_name = serializer.data["customer"].get("schema_name")
        self.assertIsNotNone(schema_name)
        self.assertEqual(schema_name, expected_schema_name)
