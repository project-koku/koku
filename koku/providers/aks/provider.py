#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Azure Kubernetes Service provider implementation to be used by Koku."""
from api.provider.models import Provider
from ..third_party_kubernetes_provider import ThirdPartyKubernetesProvider


class AKSProvider(ThirdPartyKubernetesProvider):
    """Provider interface definition for Azure Kubernetes Service."""

    provider_name = Provider.PROVIDER_AKS
    infra_provider = Provider.PROVIDER_AZURE
