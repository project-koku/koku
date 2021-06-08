#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""IBM-local service provider implementation to be used by Koku."""
from rest_framework import serializers

from ..ibm.provider import IBMProvider
from api.common import error_obj
from api.models import Provider


class IBMLocalProvider(IBMProvider):
    """IBM local provider."""

    def name(self):
        """Return name of the provider."""
        return Provider.PROVIDER_IBM_LOCAL

    def cost_usage_source_is_reachable(self, credentials, data_source):
        """Verify that IBM local enterprise id is given."""
        if not data_source:
            key = "data_source.enterprise_id"
            message = "Enterprise ID is a required parameter for IBM local."
            raise serializers.ValidationError(error_obj(key, message))
        return True
