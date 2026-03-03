#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Base provider implementation for third-party managed Kubernetes services."""
import logging

from rest_framework import serializers

from .provider_interface import ProviderInterface
from api.common import error_obj

LOG = logging.getLogger(__name__)


class ThirdPartyKubernetesProvider(ProviderInterface):
    """Base class for third-party managed Kubernetes providers (EKS, AKS, GKE).

    Subclasses must define:
        provider_name    -- the Provider.PROVIDER_* constant for this service
        infra_provider   -- the Provider.PROVIDER_* constant for the backing cloud
    """

    provider_name = None
    infra_provider = None

    def name(self):
        """Return name of the provider."""
        return self.provider_name

    def cost_usage_source_is_reachable(self, credential, data_source):
        """Verify that the cost usage source exists and is reachable."""
        cluster_id = credential.get("cluster_id")
        if not cluster_id:
            key = "authentication.cluster_id"
            message = f"Provider resource name is a required parameter for {self.provider_name}."
            LOG.info(message)
            raise serializers.ValidationError(error_obj(key, message))
        if data_source:
            key = "billing_source.bucket"
            message = f"Bucket is an invalid parameter for {self.provider_name}."
            LOG.error(message)
            raise serializers.ValidationError(error_obj(key, message))

        # TODO: Add connectivity check once operator integration is defined.
        message = f"Stub to verify that {self.provider_name} report for cluster {cluster_id} is accessible."
        LOG.info(message)

        return True

    def infra_type_implementation(self, provider_uuid, tenant):
        """Return the backing cloud infrastructure type."""
        return self.infra_provider

    def infra_key_list_implementation(self, infrastructure_type, schema_name):
        """Return a list of cluster ids on the given infrastructure type."""
        return []
