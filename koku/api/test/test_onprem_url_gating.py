#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for on-prem gating of cloud / OCP-on-cloud customer API routes."""
from django.test import SimpleTestCase
from django.urls import URLPattern
from django.urls import URLResolver

from api.urls import build_api_urlpatterns
from api.urls import get_onprem_only_urlpatterns
from api.urls import get_saas_only_urlpatterns


ONPREM_ONLY_ROUTE_NAMES = frozenset({"source-types", "application-types", "applications", "data-retention"})

# Representative pure-cloud named routes (AWS / Azure / GCP + cloud resource types / orgs).
CLOUD_ROUTE_NAMES = (
    "reports-aws-costs",
    "aws-tags",
    "gcp-cost-forecasts",
    "azure-cost-forecasts",
    "aws-cost-forecasts",
    "cloud-accounts",
    "aws-accounts",
    "aws-org-unit",
    "settings-aws-category-keys",
    "reports-azure-costs",
    "reports-gcp-costs",
    "azure-tags",
    "gcp-tags",
    "gcp-accounts",
    "azure-subscription-guids",
)

# Representative OCP-on-cloud infrastructure routes.
OCP_ON_CLOUD_ROUTE_NAMES = (
    "reports-openshift-aws-costs",
    "openshift-azure-tags",
    "openshift-gcp-cost-forecasts",
    "reports-openshift-azure-costs",
    "reports-openshift-gcp-costs",
    "openshift-aws-tags",
    "openshift-aws-cost-forecasts",
    "openshift-azure-cost-forecasts",
)

# Representative OCP-only / shared routes that must remain on-prem.
OCP_AND_SHARED_ROUTE_NAMES = (
    "reports-openshift-costs",
    "openshift-clusters",
    "server-status",
    "openshift-tags",
    "openshift-cost-forecasts",
    "currency",
    "resource-types",
    "settings-cost-groups",
)


def _collect_url_names(urlpatterns):
    """Collect named routes from a urlpatterns list (including nested includes)."""
    names = set()
    for pattern in urlpatterns:
        if isinstance(pattern, URLResolver):
            names.update(_collect_url_names(pattern.url_patterns))
        elif isinstance(pattern, URLPattern) and pattern.name:
            names.add(pattern.name)
    return names


class OnPremUrlGatingTest(SimpleTestCase):
    """URL registration helpers gate cloud / OCP-on-cloud routes by onprem flag."""

    def test_cloud_named_routes_absent_when_onprem(self):
        """Pure cloud customer routes are not registered when onprem=True."""
        names = _collect_url_names(build_api_urlpatterns(onprem=True))
        for route_name in CLOUD_ROUTE_NAMES:
            with self.subTest(route_name=route_name):
                self.assertNotIn(route_name, names)

    def test_ocp_on_cloud_named_routes_absent_when_onprem(self):
        """OCP-on-cloud infrastructure routes are not registered when onprem=True."""
        names = _collect_url_names(build_api_urlpatterns(onprem=True))
        for route_name in OCP_ON_CLOUD_ROUTE_NAMES:
            with self.subTest(route_name=route_name):
                self.assertNotIn(route_name, names)

    def test_cloud_and_ocp_on_cloud_routes_present_when_not_onprem(self):
        """Cloud and OCP-on-cloud routes remain registered for SaaS (onprem=False)."""
        names = _collect_url_names(build_api_urlpatterns(onprem=False))
        for route_name in (*CLOUD_ROUTE_NAMES, *OCP_ON_CLOUD_ROUTE_NAMES):
            with self.subTest(route_name=route_name):
                self.assertIn(route_name, names)

    def test_ocp_and_shared_routes_present_when_onprem(self):
        """OCP-only and shared customer routes remain registered when onprem=True."""
        names = _collect_url_names(build_api_urlpatterns(onprem=True))
        for route_name in OCP_AND_SHARED_ROUTE_NAMES:
            with self.subTest(route_name=route_name):
                self.assertIn(route_name, names)
        # sources is registered via DefaultRouter
        self.assertTrue(any(name.startswith("sources") for name in names))

    def test_all_saas_only_names_absent_when_onprem(self):
        """Every saas-only path name is omitted from the on-prem urlpatterns."""
        saas_names = {p.name for p in get_saas_only_urlpatterns() if getattr(p, "name", None)}
        names_onprem = _collect_url_names(build_api_urlpatterns(onprem=True))
        self.assertTrue(saas_names)
        self.assertTrue(saas_names.isdisjoint(names_onprem))

    def test_onprem_only_routes_present_when_onprem(self):
        """CMMO + data-retention routes are registered only when onprem=True."""
        names_onprem = _collect_url_names(build_api_urlpatterns(onprem=True))
        names_saas = _collect_url_names(build_api_urlpatterns(onprem=False))
        onprem_helper_names = {p.name for p in get_onprem_only_urlpatterns() if getattr(p, "name", None)}
        # data-retention is inserted into shared patterns, not get_onprem_only_urlpatterns
        expected = ONPREM_ONLY_ROUTE_NAMES
        self.assertTrue(onprem_helper_names.issubset(expected))
        self.assertTrue(expected.issubset(names_onprem))
        self.assertTrue(expected.isdisjoint(names_saas))

    def test_sources_aws_s3_regions_absent_when_onprem(self):
        """AWS S3 regions Sources action is not registered on-prem."""
        names_onprem = _collect_url_names(build_api_urlpatterns(onprem=True))
        names_saas = _collect_url_names(build_api_urlpatterns(onprem=False))
        self.assertNotIn("sources-aws-s3-regions", names_onprem)
        self.assertIn("sources-aws-s3-regions", names_saas)
