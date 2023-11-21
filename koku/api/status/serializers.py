#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializer to capture server status."""
from rest_framework import serializers

from .models import Status


class ConfigSerializer(serializers.Serializer):
    """Serializer for the Config class"""

    debug = serializers.BooleanField(source="DEBUG", read_only=True)
    account_access_type = serializers.CharField(source="ACCOUNT_ACCESS_TYPE", read_only=True)
    csv_data_type = serializers.CharField(source="CSV_DATA_TYPE", read_only=True)
    parquet_data_type = serializers.CharField(source="PARQUET_DATA_TYPE", read_only=True)
    report_processing_batch_size = serializers.IntegerField(source="REPORT_PROCESSING_BATCH_SIZE", read_only=True)
    aws_datetime_str_format = serializers.CharField(source="AWS_DATETIME_STR_FORMAT", read_only=True)
    ocp_datetime_str_format = serializers.CharField(source="OCP_DATETIME_STR_FORMAT", read_only=True)
    azure_datetime_str_format = serializers.CharField(source="AZURE_DATETIME_STR_FORMAT", read_only=True)
    masu_date_override = serializers.CharField(source="MASU_DATE_OVERRIDE", read_only=True)
    masu_retain_num_months = serializers.IntegerField(source="MASU_RETAIN_NUM_MONTHS", read_only=True)
    masu_retain_num_months_line_item_only = serializers.IntegerField(
        source="MASU_RETAIN_NUM_MONTHS_LINE_ITEM_ONLY", read_only=True
    )
    initial_ingest_num_months = serializers.IntegerField(source="INITIAL_INGEST_NUM_MONTHS", read_only=True)
    ingest_override = serializers.BooleanField(source="INGEST_OVERRIDE", read_only=True)
    trino_enabled = serializers.BooleanField(default=True)

    kafka_connect = serializers.BooleanField(source="KAFKA_CONNECT", read_only=True)
    retry_seconds = serializers.IntegerField(source="RETRY_SECONDS", read_only=True)
    del_record_limit = serializers.IntegerField(source="DEL_RECORD_LIMIT", read_only=True)
    max_iterations = serializers.IntegerField(source="MAX_ITERATIONS", read_only=True)


class StatusSerializer(serializers.Serializer):
    """Serializer for the Status model."""

    api_version = serializers.IntegerField()
    commit = serializers.CharField()
    modules = serializers.DictField()
    platform_info = serializers.DictField()
    python_version = serializers.CharField()
    rbac_cache_ttl = serializers.CharField()
    config = ConfigSerializer()

    class Meta:
        """Metadata for the serializer."""

        model = Status
        fields = "__all__"
