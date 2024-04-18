#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the Masu API `manifest` Serializers."""
from rest_framework.serializers import ValidationError

from api.provider.models import Provider
from api.provider.models import Sources
from masu.api.sources.serializers import CustomerSerializer
from masu.api.sources.serializers import ProviderInfrastructureSerializer
from masu.api.sources.serializers import ProviderSerializer
from masu.api.sources.serializers import SourceSerializer
from masu.test import MasuTestCase


class SourceSerializerTest(MasuTestCase):
    """Source serializer tests"""

    def setUp(self):
        super().setUp()
        providers = Provider.objects.all()
        self.data = []
        for i, provider in enumerate(providers):
            datum = {
                "source_id": i,
                "source_uuid": provider.uuid,
                "name": provider.name,
                "auth_header": "abc1234",
                "offset": i,
                "account_id": self.acct,
                "org_id": self.org_id,
                "source_type": provider.type,
                "authentication": provider.authentication.credentials,
                "billing_source": provider.billing_source.data_source,
                "koku_uuid": str(provider.uuid),
                "pending_delete": False,
                "pending_update": False,
                "out_of_order_delete": False,
                "status": {},
                "paused": False,
                "provider": provider,
            }
            Sources(**datum).save()
            self.data.append(datum)

    def test_serializer(self):
        """Test the serializer."""
        for entry in self.data:
            provider = entry.get("provider")
            customer = provider.customer
            infrastructure = provider.infrastructure

            customer_data = {"id": customer.id, "schema_name": customer.schema_name}
            customer_serializer = CustomerSerializer(data=customer_data, context=self.request_context)
            customer_serializer.is_valid()
            validated_customer = customer_serializer.data

            provider_data = {
                "uuid": provider.uuid,
                "setup_complete": provider.setup_complete,
                "created_timestamp": provider.created_timestamp,
                "data_updated_timestamp": provider.data_updated_timestamp,
                "active": provider.active,
                "paused": provider.paused,
                "customer": validated_customer,
            }
            if infrastructure:
                infrastructure_data = {
                    "id": infrastructure.id,
                    "infrastructure_type": infrastructure.infrastructure_type,
                    "infrastructure_provider_id": infrastructure.infrastructure_provider_id,
                }
                infrastructure_serializer = ProviderInfrastructureSerializer(
                    data=infrastructure_data, context=self.request_context
                )
                infrastructure_serializer.is_valid()
                provider_data["infrastructure"] = infrastructure_serializer.data

            provider_serializer = ProviderSerializer(data=provider_data, context=self.request_context)
            provider_serializer.is_valid()
            validated_provider = provider_serializer.data

            with self.assertRaises(ValidationError):
                serializer = SourceSerializer(data=entry, context=self.request_context)
                serializer.is_valid(raise_exception=True)

            entry["provider"] = validated_provider
            serializer = SourceSerializer(data=entry, context=self.request_context)
            self.assertTrue(serializer.is_valid(raise_exception=True))
