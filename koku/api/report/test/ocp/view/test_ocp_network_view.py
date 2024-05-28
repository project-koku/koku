#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.urls import reverse
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.utils import DateHelper
from reporting.provider.ocp.models import OCPNetworkSummaryByNodeP
from reporting.provider.ocp.models import OCPNetworkSummaryP


class OCPReportViewNetworkTest(IamTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.date_helper = DateHelper()
        cls.ten_days_ago = cls.date_helper.n_days_ago(cls.date_helper.now, 9)

    def setUp(self) -> None:
        super().setUp()

        self.url = reverse("reports-openshift-network")
        self.client = APIClient()

        with schema_context(self.schema_name):
            self.total_in = sum(
                OCPNetworkSummaryP.objects.filter(
                    usage_start__gte=self.ten_days_ago.date(), infrastructure_data_in_gigabytes__isnull=False
                ).values_list("infrastructure_data_in_gigabytes", flat=True)
            )
            self.total_out = sum(
                OCPNetworkSummaryP.objects.filter(
                    usage_start__gte=self.ten_days_ago.date(), infrastructure_data_out_gigabytes__isnull=False
                ).values_list("infrastructure_data_out_gigabytes", flat=True)
            )
            self.nodes = set(OCPNetworkSummaryByNodeP.objects.values_list("node", flat=True).distinct())
            self.clusters = set(OCPNetworkSummaryP.objects.values_list("cluster_alias", flat=True).distinct())

        self.total = self.total_in + self.total_out

    def test_get_node_network_costs(self):
        with schema_context(self.schema_name):
            response = self.client.get(self.url, **self.headers)

        data = response.data
        meta = data.get("meta")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(meta["total"]["data_transfer_in"], self.total_in)
        self.assertEqual(meta["total"]["data_transfer_out"], self.total_out)
        self.assertEqual(meta["total"]["usage"], self.total)

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
