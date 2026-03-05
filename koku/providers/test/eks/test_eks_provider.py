#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the EKSProvider implementation for the Koku interface."""
from api.models import Provider
from providers.eks.provider import EKSProvider
from providers.test.third_party_kubernetes_test_base import ThirdPartyKubernetesProviderTestBase


class EKSProviderTestCase(ThirdPartyKubernetesProviderTestBase):
    """Test cases for EKSProvider."""

    provider_class = EKSProvider
    provider_name = Provider.PROVIDER_EKS
    infra_provider = Provider.PROVIDER_AWS
    cluster_prefix = "eks"
