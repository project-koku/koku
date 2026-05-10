#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common Test utilities."""
from decimal import Decimal

from django_tenants.utils import schema_context

from api.metrics import constants as metric_constants
from api.report.test.util.constants import OCP_PLATFORM_NAMESPACE
from cost_models.cost_model_manager import derive_metric_type
from cost_models.cost_model_manager import generate_custom_name
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.models import Rate
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


def sync_test_rate_rows(cost_model):
    """Create PriceList, Rate, and PriceListCostModelMap rows from a CostModel's JSON rates.

    Mirrors the dual-write performed by rate_sync.sync_rate_table() but
    operates directly from the JSON blob.  Used in test data loaders so that
    the Rate-table-backed CostModelDBAccessor.price_list property works in tests.
    """
    if not cost_model.rates:
        return

    metrics_map = metric_constants.get_cost_model_metrics_map()
    pl = PriceList.objects.create(
        name=f"Test PriceList for {cost_model.name}",
        description="Auto-generated for unit tests",
        currency=getattr(cost_model, "currency", "USD"),
        effective_start_date="2020-01-01",
        effective_end_date="2099-12-31",
        rates=cost_model.rates,
    )
    PriceListCostModelMap.objects.create(price_list=pl, cost_model=cost_model, priority=1)

    seen_names = set()
    rate_objects = []
    for rate_data in cost_model.rates:
        metric_name = rate_data.get("metric", {}).get("name", "")
        cost_type = rate_data.get("cost_type", "")
        if not cost_type:
            cost_type = metrics_map.get(metric_name, {}).get("default_cost_type", "Supplementary")
        rate_data["cost_type"] = cost_type

        tag_rates = rate_data.get("tag_rates") or {}
        tag_key = tag_rates.get("tag_key", "")
        tag_values = tag_rates.get("tag_values", [])

        tiered = rate_data.get("tiered_rates") or []
        default_rate = Decimal(str(tiered[0].get("value", 0))) if tiered else None

        metric_type = derive_metric_type(metric_name)

        custom_name = rate_data.get("custom_name", "")
        if not custom_name:
            custom_name = generate_custom_name(rate_data, seen_names)
        seen_names.add(custom_name)

        rate_objects.append(
            Rate(
                price_list=pl,
                custom_name=custom_name,
                description=rate_data.get("description", ""),
                metric=metric_name,
                metric_type=metric_type,
                cost_type=cost_type,
                default_rate=default_rate,
                tag_key=tag_key,
                tag_values=tag_values,
            )
        )
    Rate.objects.bulk_create(rate_objects)
