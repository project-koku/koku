#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider Mapper for OCP Reports."""
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import CharField
from django.db.models import DecimalField
from django.db.models import F
from django.db.models import Max
from django.db.models import Q
from django.db.models import Sum
from django.db.models import Value
from django.db.models.functions import Coalesce

from api.models import Provider
from api.report.provider_map import ProviderMap
from koku.database import KeyDecimalTransform
from providers.provider_access import ProviderAccessor
from reporting.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPCostSummaryByNodeP
from reporting.provider.ocp.models import OCPCostSummaryByProjectP
from reporting.provider.ocp.models import OCPCostSummaryP
from reporting.provider.ocp.models import OCPPodSummaryByProjectP
from reporting.provider.ocp.models import OCPPodSummaryP
from reporting.provider.ocp.models import OCPVolumeSummaryByProjectP
from reporting.provider.ocp.models import OCPVolumeSummaryP


class OCPProviderMap(ProviderMap):
    """OCP Provider Map."""

    def __init__(self, provider, report_type):
        """Constructor."""
        self._mapping = [
            {
                "provider": Provider.PROVIDER_OCP,
                "annotations": {"cluster": "cluster_id"},
                "end_date": "usage_end",
                "filters": {
                    "project": {"field": "namespace", "operation": "icontains"},
                    "cluster": [
                        {"field": "cluster_alias", "operation": "icontains", "composition_key": "cluster_filter"},
                        {"field": "cluster_id", "operation": "icontains", "composition_key": "cluster_filter"},
                    ],
                    "pod": {"field": "pod", "operation": "icontains"},
                    "node": {"field": "node", "operation": "icontains"},
                    "infrastructures": {
                        "field": "cluster_id",
                        "operation": "exact",
                        "custom": ProviderAccessor(Provider.PROVIDER_OCP).infrastructure_key_list,
                    },
                },
                "group_by_options": ["cluster", "project", "node"],
                "tag_column": "pod_labels",
                "report_type": {
                    "costs": {
                        "tables": {"query": OCPUsageLineItemDailySummary},
                        "aggregates": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                        },
                        "default_ordering": {"cost_total": "desc"},
                        "annotations": {
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            # Cost =  Supplementary[field] + Infrastructure[filed]
                            # Note: if a value was currently zero it was left out, unless both sup & infra are zero
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_units": Value("USD", output_field=CharField()),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "capacity_aggregate": {},
                        "delta_key": {
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            )
                        },
                        "filter": [{}],
                        "cost_units_key": "USD",
                        "sum_columns": ["cost_total", "infra_total", "sup_total"],
                    },
                    "costs_by_project": {
                        "tables": {"query": OCPUsageLineItemDailySummary},
                        "aggregates": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_markup": Sum(
                                Coalesce(
                                    F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField())
                                )
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField())
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            # Cost =  Supplementary[field] + Infrastructure[filed]
                            # Note: if a value was currently zero it was left out, unless both sup & infra are zero
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_markup": Sum(
                                Coalesce(
                                    F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField())
                                )
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField())
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                        },
                        "default_ordering": {"cost_total": "desc"},
                        "annotations": {
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_markup": Sum(
                                Coalesce(
                                    F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField())
                                )
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField())
                                )
                            ),
                            # Cost =  Supplementary[field] + Infrastructure[filed]
                            # Note: if a value was currently zero it was left out, unless both sup & infra are zero
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_markup": Sum(
                                Coalesce(
                                    F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField())
                                )
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField())
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_units": Value("USD", output_field=CharField()),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "cost": Value(0, output_field=DecimalField()),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "capacity_aggregate": {},
                        "delta_key": {
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField())
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_project_monthly_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            )
                        },
                        "filter": [{}],
                        "cost_units_key": "USD",
                        "sum_columns": ["cost_total", "infra_total", "sup_total"],
                    },
                    "cpu": {
                        "aggregates": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "usage": Sum("pod_usage_cpu_core_hours"),
                            "request": Sum("pod_request_cpu_core_hours"),
                            "limit": Sum("pod_limit_cpu_core_hours"),
                        },
                        "capacity_aggregate": {"capacity": Max("cluster_capacity_cpu_core_hours")},
                        "default_ordering": {"usage": "desc"},
                        "annotations": {
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_units": Value("USD", output_field=CharField()),
                            "usage_units": Value("Core-Hours", output_field=CharField()),
                            "usage": Sum("pod_usage_cpu_core_hours"),
                            "request": Sum("pod_request_cpu_core_hours"),
                            "limit": Sum("pod_limit_cpu_core_hours"),
                            "capacity": Max("cluster_capacity_cpu_core_hours"),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "delta_key": {
                            "usage": Sum("pod_usage_cpu_core_hours"),
                            "request": Sum("pod_request_cpu_core_hours"),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                        },
                        "filter": [{"field": "data_source", "operation": "exact", "parameter": "Pod"}],
                        "cost_units_key": "USD",
                        "usage_units_key": "Core-Hours",
                        "sum_columns": ["usage", "request", "limit", "sup_total", "cost_total", "infra_total"],
                    },
                    "memory": {
                        "aggregates": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "usage": Sum("pod_usage_memory_gigabyte_hours"),
                            "request": Sum("pod_request_memory_gigabyte_hours"),
                            "limit": Sum("pod_limit_memory_gigabyte_hours"),
                        },
                        "capacity_aggregate": {"capacity": Max("cluster_capacity_memory_gigabyte_hours")},
                        "default_ordering": {"usage": "desc"},
                        "annotations": {
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_units": Value("USD", output_field=CharField()),
                            "usage": Sum("pod_usage_memory_gigabyte_hours"),
                            "request": Sum("pod_request_memory_gigabyte_hours"),
                            "limit": Sum("pod_limit_memory_gigabyte_hours"),
                            "capacity": Max("cluster_capacity_memory_gigabyte_hours"),
                            "usage_units": Value("GB-Hours", output_field=CharField()),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "delta_key": {
                            "usage": Sum("pod_usage_memory_gigabyte_hours"),
                            "request": Sum("pod_request_memory_gigabyte_hours"),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                        },
                        "filter": [{"field": "data_source", "operation": "exact", "parameter": "Pod"}],
                        "cost_units_key": "USD",
                        "usage_units_key": "GB-Hours",
                        "sum_columns": ["usage", "request", "limit", "cost_total", "sup_total", "infra_total"],
                    },
                    "volume": {
                        "tag_column": "volume_labels",
                        "aggregates": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "usage": Sum("persistentvolumeclaim_usage_gigabyte_months"),
                            "request": Sum("volume_request_storage_gigabyte_months"),
                        },
                        "capacity_aggregate": {"capacity": Sum("persistentvolumeclaim_capacity_gigabyte_months")},
                        "default_ordering": {"usage": "desc"},
                        "annotations": {
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_distributed": Sum(
                                Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "usage": Sum("persistentvolumeclaim_usage_gigabyte_months"),
                            "request": Sum("volume_request_storage_gigabyte_months"),
                            "capacity": Sum("persistentvolumeclaim_capacity_gigabyte_months"),
                            "cost_units": Value("USD", output_field=CharField()),
                            "usage_units": Value("GB-Mo", output_field=CharField()),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "delta_key": {
                            "usage": Sum("persistentvolumeclaim_usage_gigabyte_months"),
                            "request": Sum("volume_request_storage_gigabyte_months"),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "infrastructure_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("pvc", "supplementary_monthly_cost_json"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                        },
                        "filter": [{"field": "data_source", "operation": "exact", "parameter": "Storage"}],
                        "cost_units_key": "USD",
                        "usage_units_key": "GB-Mo",
                        "sum_columns": ["usage", "request", "cost_total", "sup_total", "infra_total"],
                    },
                    "tags": {"default_ordering": {"cost_total": "desc"}},
                },
                "start_date": "usage_start",
                "tables": {"query": OCPUsageLineItemDailySummary},
            }
        ]

        self.views = {
            "costs": {
                "default": OCPCostSummaryP,
                ("cluster",): OCPCostSummaryP,
                ("node",): OCPCostSummaryByNodeP,
                ("cluster", "node"): OCPCostSummaryByNodeP,
            },
            "costs_by_project": {
                "default": OCPCostSummaryByProjectP,
                ("project",): OCPCostSummaryByProjectP,
                ("cluster", "project"): OCPCostSummaryByProjectP,
            },
            "cpu": {
                "default": OCPPodSummaryP,
                ("cluster",): OCPPodSummaryP,
                ("project",): OCPPodSummaryByProjectP,
                ("cluster", "project"): OCPPodSummaryByProjectP,
            },
            "memory": {
                "default": OCPPodSummaryP,
                ("cluster",): OCPPodSummaryP,
                ("project",): OCPPodSummaryByProjectP,
                ("cluster", "project"): OCPPodSummaryByProjectP,
            },
            "volume": {
                "default": OCPVolumeSummaryP,
                ("cluster",): OCPVolumeSummaryP,
                ("project",): OCPVolumeSummaryByProjectP,
                ("cluster", "project"): OCPVolumeSummaryByProjectP,
            },
        }
        super().__init__(provider, report_type)
