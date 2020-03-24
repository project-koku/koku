from rest_framework import serializers


class CloudAccountsSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    value = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=200)
    updated_timestamp = serializers.DateTimeField()
