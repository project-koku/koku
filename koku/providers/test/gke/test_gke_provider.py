#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the GKEProvider implementation for the Koku interface."""
from api.models import Provider
from providers.gke.provider import GKEProvider
from providers.test.third_party_kubernetes_test_base import ThirdPartyKubernetesProviderTestBase


class GKEProviderTestCase(ThirdPartyKubernetesProviderTestBase):
    """Test cases for GKEProvider."""

    provider_class = GKEProvider
    provider_name = Provider.PROVIDER_GKE
    infra_provider = Provider.PROVIDER_GCP
    cluster_prefix = "gke"
