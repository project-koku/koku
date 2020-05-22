"""GCP provider implementation to be used by Koku."""
import logging

from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError
from rest_framework import serializers

from ..provider_interface import ProviderInterface
from api.common import error_obj
from api.models import Provider

LOG = logging.getLogger(__name__)


class GCPProvider(ProviderInterface):
    """GCP provider."""

    def name(self):
        """Return name of the provider."""
        return Provider.PROVIDER_GCP

    def cost_usage_source_is_reachable(self, credential_name, data_source):
        """
        Verify that the GCP bucket exists and is reachable.

        Args:
            credential_name (object): not used; only present for interface compatibility
            data_source (dict): dict containing name of GCP storage bucket

        """
        storage_client = storage.Client()
        bucket = data_source["bucket"]
        try:
            bucket_info = storage_client.lookup_bucket(bucket)
            if not bucket_info:
                # if the lookup does not return anything, then this is an nonexistent bucket
                key = "billing_source.bucket"
                message = f"The provided GCP bucket {bucket} does not exist"
                raise serializers.ValidationError(error_obj(key, message))

        except GoogleCloudError as e:
            key = "billing_source.bucket"
            raise serializers.ValidationError(error_obj(key, e.message))

        return True

    def infra_type_implementation(self, provider_uuid, tenant):
        """Return infrastructure type."""
        return None

    def infra_key_list_implementation(self, infrastructure_type, schema_name):
        """Return a list of cluster ids on the given infrastructure type."""
        return []
