#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Amazon Elastic Kubernetes Service provider implementation to be used by Koku."""
from api.provider.models import Provider
from ..third_party_kubernetes_provider import ThirdPartyKubernetesProvider


class EKSProvider(ThirdPartyKubernetesProvider):
    """Provider interface definition for Amazon Elastic Kubernetes Service."""

    provider_name = Provider.PROVIDER_EKS
    infra_provider = Provider.PROVIDER_AWS
