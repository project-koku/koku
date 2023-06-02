#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Post Report Serializers."""
from rest_framework import serializers

from api.common import error_obj
from api.utils import DateHelper
from providers.provider_access import ProviderAccessor
from reporting.ingress.models import IngressReports

PROVIDER_LIST = ["aws", "aws-local", "azure", "azure-local", "gcp", "gcp-local"]


class IngressReportsSerializer(serializers.ModelSerializer):
    """Serializer for the Ingress Reports model."""

    uuid = serializers.UUIDField(read_only=True)
    created_timestamp = serializers.DateTimeField(read_only=True)
    completed_timestamp = serializers.DateTimeField(read_only=True)
    reports_list = serializers.ListField()
    sources_id = serializers.IntegerField(required=False, allow_null=True)
    bill_year = serializers.CharField(required=True, max_length=4)
    bill_month = serializers.CharField(required=True, max_length=2)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = IngressReports
        fields = [
            "uuid",
            "created_timestamp",
            "completed_timestamp",
            "reports_list",
            "source",
            "sources_id",
            "bill_year",
            "bill_month",
            "status",
        ]

    def validate(self, data):
        """
        Check for supported sources.
        """
        source_type = data.get("source").type
        bill_year = data.get("bill_year")
        bill_month = data.get("bill_month")
        if source_type.lower() in PROVIDER_LIST:
            dh = DateHelper()
            month_range = [dh.bill_month_from_date(dh.last_month_start), dh.bill_month_from_date(dh.this_month_start)]
            year_range = [
                dh.bill_year_from_date(dh.last_month_start),
            ]
            year_message = year_range[0]
            if dh.bill_year_from_date(dh.this_month_start) not in year_range:
                year_range.append(dh.bill_year_from_date(dh.last_month_start))
                year_message = f"{year_range[0]} or {year_range[1]}"
            if bill_month in month_range and bill_year in year_range:
                interface = ProviderAccessor(source_type)
                interface.check_file_access(data.get("source"), data.get("reports_list"))
                ingress_reports = IngressReports.objects.filter(
                    source=data.get("source"),
                    bill_year=bill_year,
                    bill_month=bill_month,
                    status="pending",
                    created_timestamp__gte=DateHelper().today,
                )
                if ingress_reports:
                    key = "Processing"
                    message = f"Reports for billing month {bill_month} already in-progress!"
                    raise serializers.ValidationError(error_obj(key, message))
                return data
            key = "bill_period"
            message = (
                f"Invalid bill, year must be {year_message} and month must be {month_range[0]} or {month_range[1]}"
            )
            raise serializers.ValidationError(error_obj(key, message))
        key = "source_type"
        message = f"Invalid source_type, {source_type}, provided."
        raise serializers.ValidationError(error_obj(key, message))
