#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Utility for provider testing."""
from unittest.mock import patch

from api.provider.models import Provider
from api.provider.serializers import ProviderSerializer
from providers.provider_access import ProviderAccessor


PROVIDERS = {
    Provider.PROVIDER_OCP: {
        "name": "test_provider",
        "type": Provider.PROVIDER_OCP.lower(),
        "authentication": {"credentials": {"cluster_id": "my-ocp-cluster-1"}},
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
    "AzUrE": {
        "name": "test_provider",
        "type": "AzUrE".lower(),
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
    "oCp": {
        "name": "test_provider",
        "type": "oCp".lower(),
        "authentication": {"credentials": {"cluster_id": "my-ocp-cluster-1"}},
    },
}


def create_generic_provider(provider_type, request_context):
    """Create generic provider and return response."""
    provider_data = PROVIDERS[provider_type]
    provider = None
    with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
        serializer = ProviderSerializer(data=provider_data, context=request_context)
        if serializer.is_valid(raise_exception=True):
            provider = serializer.save()

    return {}, provider
