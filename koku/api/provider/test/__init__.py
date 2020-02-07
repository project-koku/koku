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
"""Utility for provider testing."""
from unittest.mock import patch

from django.urls import reverse
from rest_framework.test import APIClient

from api.provider.models import Provider
from providers.provider_access import ProviderAccessor


PROVIDERS = {
    Provider.PROVIDER_OCP: {
        "name": "test_provider",
        "type": Provider.PROVIDER_OCP,
        "authentication": {"credentials": {"provider_resource_name": "my-ocp-cluster-1"}},
    },
    Provider.PROVIDER_AWS: {
        "name": "test_provider",
        "type": Provider.PROVIDER_AWS,
        "authentication": {"credentials": {"provider_resource_name": "arn:aws:s3:::my_s3_bucket"}},
        "billing_source": {"data_source": {"bucket": "my_s3_bucket"}},
    },
    Provider.PROVIDER_AZURE: {
        "name": "test_provider",
        "type": Provider.PROVIDER_AZURE,
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
        "type": "AzUrE",
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
        "type": "oCp",
        "authentication": {"credentials": {"provider_resource_name": "my-ocp-cluster-1"}},
    },
}


def create_generic_provider(provider_type, headers):
    """Create generic provider and return response."""
    provider_data = PROVIDERS[provider_type]
    url = reverse("provider-list")
    with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
        client = APIClient()
        result = client.post(url, data=provider_data, format="json", **headers)
        uuid = result.json().get("uuid")
        provider = Provider.objects.get(uuid=uuid)
        return result, provider
