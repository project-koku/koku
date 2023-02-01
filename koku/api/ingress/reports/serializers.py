#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Post Report Serializers."""
import logging

from rest_framework import serializers

from api.common import error_obj
from providers.provider_access import ProviderAccessor
from reporting.ingress.models import IngressReports

LOG = logging.getLogger(__name__)

PROVIDER_LIST = ["aws", "aws-local"]


class IngressReportsSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngressReports
        fields = ["uuid", "created_timestamp", "completed_timestamp", "reports_list", "source"]

    def validate(self, data):
        """
        Check for supported sources.
        """
        source_type = data.get("source").type
        if source_type.lower() in PROVIDER_LIST:
            interface = ProviderAccessor(source_type)
            interface.check_file_access(str(data.get("source").uuid), data.get("reports_list"))
            return data
        key = "source_type"
        message = f"Invalid source_type, {source_type}, provided."
        raise serializers.ValidationError(error_obj(key, message))
