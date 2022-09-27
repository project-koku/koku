#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common Test utilities."""
from tenant_schemas.utils import schema_context

from reporting.provider.ocp.models import OCPCluster
from reporting.provider.ocp.models import OCPNode
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary


def populate_ocp_topology(schema, provider, cluster_id):
    """Populate essential OCP topology tables."""
    with schema_context(schema):
        nodes = (
            OCPUsageLineItemDailySummary.objects.filter(cluster_id=cluster_id)
            .values_list("node", "resource_id")
            .distinct()
        )
        cluster = OCPCluster(cluster_id=cluster_id, provider=provider)
        cluster.save()
        for node in nodes:
            if node[0]:
                n = OCPNode(node=node[0], resource_id=node[1], cluster=cluster)
                n.save()
