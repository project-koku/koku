#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Google Kubernetes Engine provider implementation to be used by Koku."""
from api.provider.models import Provider
from ..third_party_kubernetes_provider import ThirdPartyKubernetesProvider


class GKEProvider(ThirdPartyKubernetesProvider):
    """Provider interface definition for Google Kubernetes Engine."""

    provider_name = Provider.PROVIDER_GKE
    infra_provider = Provider.PROVIDER_GCP
