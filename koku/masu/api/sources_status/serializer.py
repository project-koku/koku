"""Serialize SourceStatus."""
from rest_framework import serializers
import sources_status


class SourcesStatusSerializer(serializers.Serializer):
    """Serialize the SourcesStatus."""

    class Meta:
        model = sources_status
        fields = ['status']
