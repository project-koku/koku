#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common Test utilities."""
from django_tenants.utils import schema_context

from api.report.test.util.constants import OCP_PLATFORM_NAMESPACE
from reporting.provider.ocp.models import OCPCluster
from reporting.provider.ocp.models import OCPNode
from reporting.provider.ocp.models import OCPProject
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OpenshiftCostCategory


def populate_ocp_topology(schema, provider, cluster_id):
    """Populate essential OCP topology tables."""
    with schema_context(schema):
        nodes = (
            OCPUsageLineItemDailySummary.objects.filter(cluster_id=cluster_id)
            .values_list("node", "resource_id")
            .distinct()
        )
        cluster = OCPCluster(cluster_id=cluster_id, provider_id=provider.uuid)
        cluster.save()
        for node in nodes:
            if node[0]:
                n = OCPNode(node=node[0], resource_id=node[1], cluster=cluster)
                n.save()
        projects = (
            OCPUsageLineItemDailySummary.objects.filter(cluster_id=cluster_id)
            .values_list("namespace", flat=True)
            .distinct()
        )
        for project in projects:
            p = OCPProject(project=project, cluster=cluster)
            p.save()


def update_cost_category(schema):
    """Update the daily summary rows to to have a cost category."""
    with schema_context(schema):
        cost_category_value = OpenshiftCostCategory.objects.first()
        rows = OCPUsageLineItemDailySummary.objects.filter(
            namespace=OCP_PLATFORM_NAMESPACE, cost_category_id__isnull=True
        )
        update_list = []
        for row in rows:
            row.cost_category = cost_category_value
            update_list.append(row)
        OCPUsageLineItemDailySummary.objects.bulk_update(update_list, ["cost_category"])
