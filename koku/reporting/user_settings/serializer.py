from rest_framework import serializers


class UserSettingsSerializer(serializers.Serializer):

    settings = serializers.JSONField(required=True)
