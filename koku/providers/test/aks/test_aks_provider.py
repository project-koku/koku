#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the AKSProvider implementation for the Koku interface."""
from api.models import Provider
from providers.aks.provider import AKSProvider
from providers.test.third_party_kubernetes_test_base import ThirdPartyKubernetesProviderTestBase


class AKSProviderTestCase(ThirdPartyKubernetesProviderTestBase):
    """Test cases for AKSProvider."""

    provider_class = AKSProvider
    provider_name = Provider.PROVIDER_AKS
    infra_provider = Provider.PROVIDER_AZURE
    cluster_prefix = "aks"
