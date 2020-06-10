"""GCP provider implementation to be used by Koku."""
from rest_framework import serializers

from ..gcp.provider import GCPProvider
from api.common import error_obj
from api.models import Provider


class GCPLocalProvider(GCPProvider):
    """GCP local provider."""

    def name(self):
        """Return name of the provider."""
        return Provider.PROVIDER_GCP_LOCAL

    def cost_usage_source_is_reachable(self, credential_name, storage_resource_name):
        """Verify that GCP local bucket name is given."""
        if not storage_resource_name:
            key = "bucket"
            message = "Bucket is a required parameter for GCP."
            raise serializers.ValidationError(error_obj(key, message))
        return True
