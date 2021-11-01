#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider Mapper for OCP on GCP Reports."""
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import CharField
from django.db.models import Count
from django.db.models import DecimalField
from django.db.models import F
from django.db.models import Max
from django.db.models import Q
from django.db.models import Sum
from django.db.models import Value
from django.db.models.expressions import ExpressionWrapper
from django.db.models.functions import Coalesce

from api.models import Provider
from api.report.provider_map import ProviderMap
from reporting.models import OCPGCPComputeSummaryP
from reporting.models import OCPGCPCostLineItemDailySummaryP
from reporting.models import OCPGCPCostLineItemProjectDailySummaryP
from reporting.models import OCPGCPCostSummaryByAccountP
from reporting.models import OCPGCPCostSummaryByGCPProjectP
from reporting.models import OCPGCPCostSummaryByRegionP
from reporting.models import OCPGCPCostSummaryByServiceP
from reporting.models import OCPGCPCostSummaryP
from reporting.models import OCPGCPDatabaseSummaryP
from reporting.models import OCPGCPNetworkSummaryP
from reporting.models import OCPGCPStorageSummaryP


class OCPGCPProviderMap(ProviderMap):
    """OCP on GCP Provider Map."""

    def __init__(self, provider, report_type):
        """Constructor."""
        self._mapping = [
            {
                "provider": Provider.OCP_GCP,
                "alias": "account_alias__account_alias",
                "annotations": {},  # Annotations that should always happen
                "group_by_annotations": {
                    "account": {"account": "account_id"},
                    "gcp_project": {"gcp_project": "project_id"},
                    "service": {"service": "service_alias"},
                    "cluster": {"cluster": "cluster_id"},
                    "project": {"project": "namespace"},
                },  # Annotations that should happen depending on group_by values
                "end_date": "usage_end",
                "filters": {
                    "account": {"field": "account_id", "operation": "icontains"},
                    "region": {"field": "region", "operation": "icontains"},
                    "service": [
                        {"field": "service_alias", "operation": "icontains", "composition_key": "service_filter"},
                        {"field": "service_id", "operation": "icontains", "composition_key": "service_filter"},
                    ],
                    "gcp_project": [
                        {"field": "project_name", "operation": "icontains", "composition_key": "project_filter"},
                        {"field": "project_id", "operation": "icontains", "composition_key": "project_filter"},
                    ],
                    "project": {"field": "namespace", "operation": "icontains"},
                    "instance_type": {"field": "instance_type", "operation": "icontains"},
                    "cluster": [
                        {"field": "cluster_alias", "operation": "icontains", "composition_key": "cluster_filter"},
                        {"field": "cluster_id", "operation": "icontains", "composition_key": "cluster_filter"},
                    ],
                    "node": {"field": "node", "operation": "icontains"},
                },
                "group_by_options": ["account", "region", "service", "project", "cluster", "node", "gcp_project"],
                "tag_column": "tags",
                "report_type": {
                    "costs": {
                        "aggregates": {
                            "infra_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("unblended_cost"),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "infra_credit": Sum(Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "sup_credit": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("unblended_cost"),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_credit": Sum(Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))),
                        },
                        "aggregate_key": "unblended_cost",
                        "annotations": {
                            "infra_raw": Sum("unblended_cost"),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "infra_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_credit": Sum(Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "sup_credit": Sum(Value(0, output_field=DecimalField())),
                            "cost_raw": Sum(Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))),
                            "cost_usage": Value(0, output_field=DecimalField()),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_credit": Sum(Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "delta_key": {
                            # cost goes to cost_total
                            "cost_total": Sum(
                                ExpressionWrapper(
                                    F("unblended_cost")
                                    + F("markup_cost")
                                    + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField())),
                                    output_field=DecimalField(),
                                )
                            )
                        },
                        "filter": [{}],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "sum_columns": ["cost_total", "infra_total", "sup_total"],
                        "default_ordering": {"cost_total": "desc"},
                    },
                    "costs_by_project": {
                        "tables": {
                            "query": OCPGCPCostLineItemProjectDailySummaryP,
                            "total": OCPGCPCostLineItemProjectDailySummaryP,
                        },
                        "tag_column": "tags",
                        "aggregates": {
                            "infra_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("pod_cost"),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("pod_cost"),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                        },
                        "annotations": {
                            "infra_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("pod_cost"),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("pod_cost"),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        # "count": None,
                        "delta_key": {
                            "cost_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            )
                        },
                        "filter": [{}],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "sum_columns": ["cost_total", "sup_total", "infra_total"],
                        "default_ordering": {"cost_total": "desc"},
                    },
                    "instance_type": {
                        "aggregates": {
                            "infra_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("unblended_cost"),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "infra_credit": Sum(Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "sup_credit": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("unblended_cost"),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_credit": Sum(Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "usage": Sum(F("usage_amount")),
                            "usage_units": Coalesce(Max("unit"), Value("hour")),
                        },
                        "aggregate_key": "usage_amount",
                        "annotations": {
                            "infra_raw": Sum("unblended_cost"),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "infra_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_credit": Sum(Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "sup_credit": Sum(Value(0, output_field=DecimalField())),
                            "cost_raw": Sum(Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))),
                            "cost_usage": Value(0, output_field=DecimalField()),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_credit": Sum(Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                            "usage": Sum(F("usage_amount")),
                            "usage_units": Coalesce(Max("unit"), Value("hour")),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                        },
                        "delta_key": {"usage": Sum("usage_amount")},
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "sum_columns": ["usage", "cost_total", "sup_total", "infra_total", "count"],
                        "default_ordering": {"usage": "desc"},
                        "filter": [{"field": "instance_type", "operation": "isnull", "parameter": False}],
                        "group_by": ["instance_type"],
                        "usage_units_key": "unit",
                        "usage_units_fallback": "hour",
                        "count_units_fallback": "instances",
                    },
                    "instance_type_by_project": {
                        "tables": {
                            "query": OCPGCPCostLineItemProjectDailySummaryP,
                            "total": OCPGCPCostLineItemProjectDailySummaryP,
                        },
                        "tag_column": "tags",
                        "aggregates": {
                            "infra_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("pod_cost"),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("pod_cost"),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "count": Count("resource_id", distinct=True),
                            "usage": Sum("usage_amount"),
                            "usage_units": Coalesce(Max("unit"), Value("hour")),
                        },
                        "aggregate_key": "usage_amount",
                        "annotations": {
                            "infra_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("pod_cost"),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("pod_cost"),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "count": Count("resource_id", distinct=True),
                            "count_units": Value("instances", output_field=CharField()),
                            "usage": Sum("usage_amount"),
                            "usage_units": Coalesce(Max("unit"), Value("hour")),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "count": "resource_id",
                        "delta_key": {"usage": Sum("usage_amount")},
                        "filter": [{"field": "instance_type", "operation": "isnull", "parameter": False}],
                        "group_by": ["instance_type"],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit",
                        "usage_units_fallback": "hour",
                        "count_units_fallback": "instances",
                        "sum_columns": ["usage", "cost_total", "sup_total", "infra_total", "count"],
                        "default_ordering": {"usage": "desc"},
                    },
                    "storage": {
                        "aggregates": {
                            "infra_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("unblended_cost"),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "infra_credit": Sum(Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "sup_credit": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("unblended_cost"),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_credit": Sum(Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "usage": Sum(F("usage_amount")),
                            "usage_units": Coalesce(Max("unit"), Value("gibibyte month")),
                        },
                        "aggregate_key": "usage_amount",
                        "annotations": {
                            "infra_raw": Sum("unblended_cost"),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "infra_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_credit": Sum(Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "sup_credit": Sum(Value(0, output_field=DecimalField())),
                            "cost_raw": Sum(Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))),
                            "cost_usage": Value(0, output_field=DecimalField()),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_credit": Sum(Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                            "usage": Sum(F("usage_amount")),
                            "usage_units": Coalesce(Max("unit"), Value("gibibyte month")),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                        },
                        # "count": None,
                        "delta_key": {"usage": Sum("usage_amount")},
                        "filter": [{"field": "unit", "operation": "exact", "parameter": "gibibyte month"}],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "sum_columns": ["usage", "cost_total", "infra_total", "sup_total"],
                        "default_ordering": {"cost_total": "desc"},
                    },
                    "storage_by_project": {
                        "tables": {
                            "query": OCPGCPCostLineItemProjectDailySummaryP,
                            "total": OCPGCPCostLineItemProjectDailySummaryP,
                        },
                        "tag_column": "tags",
                        "aggregates": {
                            "infra_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("pod_cost"),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("pod_cost"),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "usage": Sum("usage_amount"),
                            "usage_units": Coalesce(Max("unit"), Value("gibibyte month")),
                        },
                        "annotations": {
                            "infra_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("pod_cost"),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("pod_cost"),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "usage": Sum("usage_amount"),
                            "usage_units": Coalesce(Max("unit"), Value("gibibyte month")),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        # "count": None,
                        "delta_key": {"usage": Sum("usage_amount")},
                        "filter": [{"field": "unit", "operation": "exact", "parameter": "gibibyte month"}],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit",
                        "usage_units_fallback": "gibibyte month",
                        "sum_columns": ["usage", "cost_total", "sup_total", "infra_total"],
                        "default_ordering": {"usage": "desc"},
                    },
                    "tags": {"default_ordering": {"cost_total": "desc"}},
                },
                "start_date": "usage_start",
                "tables": {"query": OCPGCPCostLineItemDailySummaryP, "total": OCPGCPCostLineItemDailySummaryP},
            }
        ]

        self.views = {
            "costs": {
                "default": OCPGCPCostSummaryP,
                ("account",): OCPGCPCostSummaryByAccountP,
                ("gcp_project",): OCPGCPCostSummaryByGCPProjectP,
                ("region",): OCPGCPCostSummaryByRegionP,
                ("account", "region"): OCPGCPCostSummaryByRegionP,
                ("service",): OCPGCPCostSummaryByServiceP,
                ("account", "service"): OCPGCPCostSummaryByServiceP,
            },
            "instance_type": {
                "default": OCPGCPComputeSummaryP,
                ("instance_type",): OCPGCPComputeSummaryP,
                ("account", "instance_type"): OCPGCPComputeSummaryP,
                ("account",): OCPGCPComputeSummaryP,
            },
            "storage": {"default": OCPGCPStorageSummaryP, ("account",): OCPGCPStorageSummaryP},
            "database": {
                "default": OCPGCPDatabaseSummaryP,
                ("service",): OCPGCPDatabaseSummaryP,
                ("account", "service"): OCPGCPDatabaseSummaryP,
                ("account",): OCPGCPDatabaseSummaryP,
            },
            "network": {
                "default": OCPGCPNetworkSummaryP,
                ("service",): OCPGCPNetworkSummaryP,
                ("account", "service"): OCPGCPNetworkSummaryP,
                ("account",): OCPGCPNetworkSummaryP,
            },
        }
        super().__init__(provider, report_type)
