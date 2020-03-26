"""Serializer for CloudAccount."""
from rest_framework import serializers


class CloudAccountSerializer(serializers.Serializer):
    """Serializer for CloudAccount."""

    name = serializers.CharField()
    value = serializers.CharField()
    description = serializers.CharField()
    updated_timestamp = serializers.DateTimeField()
