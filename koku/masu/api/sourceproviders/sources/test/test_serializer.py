#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the Masu API `manifest` Serializers."""
from rest_framework import serializers
from tenant_schemas.utils import tenant_context

from api.iam.models import Customer
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.models import Sources
from masu.api.sourceproviders.sources.serializers import SourceSerializer


class SourceserializerTest(IamTestCase):
    """Provider serializer tests"""

    def setUp(self):
        super().setUp()
        self.test_account = "10001"
        user_data = self._create_user_data()
        customer = self._create_customer_data(account=self.test_account)
        self.request_context = self._create_request_context(customer, user_data, create_customer=True, is_admin=True)
        self.test_source_id = 1
        name = "Test sources"
        customer_obj = Customer.objects.get(account_id=customer.get("account_id"))
        self.aws_provider = Provider(name=name, type=Provider.PROVIDER_AWS, customer=customer_obj)
        self.aws_provider.save()
        self.source = Sources(
            source_id=self.test_source_id,
            source_uuid=self.aws_provider.uuid,
            name=name,
            auth_header=self.request_context["request"].META,
            offset=1,
            account_id=customer.get("account_id"),
            source_type=Provider.PROVIDER_AWS,
            authentication={
                "credentials": {"client_id": "test_client", "tenant_id": "test_tenant", "client_secret": "test_secret"}
            },
            billing_source={
                "data_source": {
                    "resource_group": {"directory": "", "export_name": "azure-report-v2"},
                    "storage_account": {"container": "", "local_dir": "/tmp/local_container"},
                }
            },
            koku_uuid=self.aws_provider.uuid,
            paused=False,
            pending_delete=False,
            pending_update=False,
            out_of_order_delete=False,
            status={},
        )
        self.source.save()
        self.serializer = SourceSerializer(self.source)
        self.basic_model = {
            "source_id": 2,
            "source_uuid": self.source.source_uuid,
            "name": "Test Provider Source",
            "auth_header": "testheader",
            "offset": 3,
            "account_id": "10001",
            "source_type": "provider",
            "authentication": self.source.authentication,
            "billing_source": self.source.billing_source,
            "pending_delete": False,
            "pending_update": False,
            "koku_uuid": self.source.source_uuid,
            "out_of_order_delete": False,
            "status": {},
            "paused": False,
        }

    def test_provider_contains_expected_fields(self):
        """Tests ProviderSerializer is utilizing expected fields"""
        data = self.serializer.data
        # TODO
        # Have to make all the keys in the fake source above
        self.assertEqual(
            set(data.keys()),
            {
                "source_id",
                "source_uuid",
                "koku_uuid",
                "name",
                "auth_header",
                "offset",
                "account_id",
                "source_type",
                "authentication",
                "billing_source",
                "pending_delete",
                "pending_update",
                "out_of_order_delete",
                "status",
                "paused",
            },
        )

    def test_valid_data(self):
        """Tests SourceSerializer with all valid data."""
        with tenant_context(self.tenant):
            serializer = SourceSerializer(data=self.basic_model)
            self.assertTrue(serializer.is_valid(raise_exception=True))

    def test_invalid_string_data(self):
        """Tests SourceSerializer invalid string."""
        self.basic_model["uuid"] = 1
        serializer = SourceSerializer(data=self.basic_model)
        self.assertRaises(TypeError, serializer.is_valid(raise_exception=True))

    def test_invalid_boolean_data(self):
        """Tests SourceSerializer invalid boolean."""
        self.basic_model["paused"] = 27
        with tenant_context(self.tenant):
            serializer = SourceSerializer(data=self.basic_model)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()
