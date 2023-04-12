#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""AWS-local service provider implementation to be used by Koku."""
from rest_framework import serializers

from ..aws.provider import AWSProvider
from ..provider_errors import ProviderErrors
from api.common import error_obj
from api.models import Provider


class AWSLocalProvider(AWSProvider):
    """Provider interface defnition."""

    def name(self):
        """Return name of the provider."""
        return Provider.PROVIDER_AWS_LOCAL

    def cost_usage_source_is_reachable(self, _, data_source):
        """Verify that the cost usage source exists and is reachable."""
        storage_resource_name = data_source.get("bucket")
        if not storage_resource_name:
            key = ProviderErrors.AWS_BUCKET_MISSING
            message = ProviderErrors.AWS_BUCKET_MISSING_MESSAGE
            raise serializers.ValidationError(error_obj(key, message))
        return True
