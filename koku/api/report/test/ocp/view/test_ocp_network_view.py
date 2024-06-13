#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.urls import reverse
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.report.ocp.provider_map import OCPProviderMap
from api.utils import DateHelper
from reporting.provider.ocp.models import OCPNetworkSummaryByNodeP
from reporting.provider.ocp.models import OCPNetworkSummaryP


class OCPReportViewNetworkTest(IamTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.date_helper = DateHelper()
        cls.ten_days_ago = cls.date_helper.n_days_ago(cls.date_helper.now, 9)
        cls.provider_map = OCPProviderMap(Provider.PROVIDER_OCP, "costs", cls.schema_name)

        cls.url = reverse("reports-openshift-network")
        cls.client = APIClient()

        with schema_context(cls.schema_name):
            cls.total_usage_in = sum(
                OCPNetworkSummaryP.objects.filter(
                    usage_start__gte=cls.ten_days_ago.date(), infrastructure_data_in_gigabytes__isnull=False
                ).values_list("infrastructure_data_in_gigabytes", flat=True)
            )
            cls.total_usage_out = sum(
                OCPNetworkSummaryP.objects.filter(
                    usage_start__gte=cls.ten_days_ago.date(), infrastructure_data_out_gigabytes__isnull=False
                ).values_list("infrastructure_data_out_gigabytes", flat=True)
            )
            cls.nodes = set(OCPNetworkSummaryByNodeP.objects.values_list("node", flat=True).distinct())
            cls.clusters = set(OCPNetworkSummaryP.objects.values_list("cluster_alias", flat=True).distinct())
            cls.total_cost = sum(
                OCPNetworkSummaryP.objects.filter(
                    usage_start__gte=cls.ten_days_ago.date(), infrastructure_raw_cost__isnull=False
                ).values_list("infrastructure_raw_cost", flat=True)
            )

        cls.total_usage = cls.total_usage_in + cls.total_usage_out

    def test_get_node_network_costs_total_usage(self):
        with schema_context(self.schema_name):
            response = self.client.get(self.url, **self.headers)

        data = response.data
        meta = data.get("meta")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(meta["total"]["data_transfer_in"]["value"], self.total_usage_in)
        self.assertEqual(meta["total"]["data_transfer_out"]["value"], self.total_usage_out)
        self.assertEqual(meta["total"]["usage"]["value"], self.total_usage)

    def test_get_node_network_costs_group_by_project(self):
        with schema_context(self.schema_name):
            params = {
                "group_by[project]": "*",
            }
            response = self.client.get(self.url, params, **self.headers)

        data = response.data
        projects = [project["project"] for item in data["data"] for project in item["projects"]]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Network unattributed", projects)

    def test_get_node_network_costs_group_by_node(self):
        with schema_context(self.schema_name):
            params = {
                "group_by[node]": "*",
            }
            response = self.client.get(self.url, params, **self.headers)

        data = response.data
        nodes = {node["node"] for item in data["data"] for node in item["nodes"]}

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.nodes, nodes)

    def test_get_node_network_costs_group_by_cluster(self):
        with schema_context(self.schema_name):
            params = {
                "group_by[cluster]": "*",
            }
            response = self.client.get(self.url, params, **self.headers)

        data = response.data
        clusters = {cluster["cluster"] for item in data["data"] for cluster in item["clusters"]}

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.clusters, clusters)

    def test_node_network_total_costs(self):
        with schema_context(self.schema_name):
            response = self.client.get(self.url, **self.headers)

        data = response.data
        total_cost = data.get("meta", {}).get("total", {}).get("cost", {}).get("total", 0).get("value", 0)

        self.assertEqual(self.total_cost, total_cost)
