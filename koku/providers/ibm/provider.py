#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""IBM provider implementation to be used by Koku."""
from ibm_cloud_sdk_core.api_exception import ApiException
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
from ibm_platform_services.enterprise_usage_reports_v1 import EnterpriseUsageReportsV1
from rest_framework import serializers

from ..provider_interface import ProviderInterface
from api.common import error_obj
from api.models import Provider


class IBMProvider(ProviderInterface):
    """IBM provider."""

    def name(self):
        """Return name of the provider."""
        return Provider.PROVIDER_IBM

    def cost_usage_source_is_reachable(self, credentials, data_source):
        """Verify that the IBM Cloud is reachable."""
        token = credentials.get("iam_token", "")
        enterprise_id = data_source.get("enterprise_id", "")
        authenticator = IAMAuthenticator(token)
        try:
            service = EnterpriseUsageReportsV1(authenticator=authenticator)
            service.get_resource_usage_report(enterprise_id=enterprise_id, children=True, limit=1)
        except ApiException as e:
            key = ""
            if "enterprise" in e.message:
                key = "data_source.enterprise_id"
            if "API key" in e.message:
                key = "credentials.iam_token"
            raise serializers.ValidationError(error_obj(key, e.message))
        return True

    def infra_type_implementation(self, provider_uuid, tenant):
        """Return infrastructure type."""
        return None

    def infra_key_list_implementation(self, infrastructure_type, schema_name):
        """Return a list of cluster ids on the given infrastructure type."""
        return []
