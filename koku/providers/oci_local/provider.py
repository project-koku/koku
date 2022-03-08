#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCI-local service provider implementation to be used by Koku."""
import logging

from rest_framework import serializers

from ..oci.provider import OCIProvider
from ..provider_errors import ProviderErrors
from api.common import error_obj
from api.models import Provider

LOG = logging.getLogger(__name__)


class OCILocalProvider(OCIProvider):
    """Provider interface defnition."""

    def name(self):
        """Return name of the provider."""
        return Provider.PROVIDER_OCI_LOCAL

    def cost_usage_source_is_reachable(self, credentials, _):
        """Verify that the cost usage source exists and is reachable."""
        tenancy = credentials.get("tenant")
        if not tenancy or tenancy.isspace():
            key = ProviderErrors.OCI_MISSING_TENANCY
            message = ProviderErrors.OCI_MISSING_TENANCY_MESSAGE
            raise serializers.ValidationError(error_obj(key, message))
        return True
