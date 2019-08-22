"""Serializers for user-initiated data exports."""
from django.db import transaction
from rest_framework import serializers

from api.dataexport.models import DataExportRequest
from api.dataexport.validators import DataExportRequestValidator


class DataExportRequestSerializer(serializers.ModelSerializer):
    """Serializer for the DataExportRequest model."""

    class Meta:
        model = DataExportRequest
        fields = (
            'uuid',
            'created_timestamp',
            'updated_timestamp',
            'start_date',
            'end_date',
            'status',
            'bucket_name',
        )
        read_only_fields = (
            'uuid',
            'created_by',
            'created_timestamp',
            'updated_timestamp',
        )
        create_only_fields = ('start_date', 'end_date', 'bucket_name')
        validators = [DataExportRequestValidator()]

    @transaction.atomic
    def create(self, validated_data):
        """Create a data export request."""
        request = self.context.get('request')
        user = request.user
        dump_request = DataExportRequest.objects.create(
            created_by=user,
            start_date=validated_data['start_date'],
            end_date=validated_data['end_date'],
            bucket_name=validated_data['bucket_name'],
        )
        return dump_request
