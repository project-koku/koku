"""GCP provider implementation to be used by Koku."""
import logging

from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError
from rest_framework import serializers

from ..provider_interface import ProviderInterface, error_obj

LOG = logging.getLogger(__name__)


class GCPProvider(ProviderInterface):
    """GCP provider."""

    def name(self):
        """Return name of the provider."""
        return 'GCP'

    def cost_usage_source_is_reachable(self, credential_name, storage_resource_name):
        """Verify that the GCP bucket exists and is reachable."""
        storage_client = storage.Client()
        try:
            bucket_info = storage_client.lookup_bucket(storage_resource_name)
            if not bucket_info:
                # if the lookup does not return anything, then this is an nonexistent bucket
                key = 'billing_source.bucket'
                message = f'The Provided GCP bucket {storage_resource_name} does not exist'
                raise serializers.ValidationError(error_obj(key, message))

        except GoogleCloudError as e:
            key = 'billing_source.bucket'
            raise serializers.ValidationError(error_obj(key, e.message))

        return True

    def infra_type_implementation(self, provider_uuid, tenant):
        """Return infrastructure type."""
        return None

    def infra_key_list_implementation(self, infrastructure_type, schema_name):
        """Return a list of cluster ids on the given infrastructure type."""
        return []
