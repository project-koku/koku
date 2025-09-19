#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider Mapper for GCP Reports."""
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import CharField
from django.db.models import DecimalField
from django.db.models import F
from django.db.models import Max
from django.db.models import Q
from django.db.models import Sum
from django.db.models import Value
from django.db.models.expressions import ExpressionWrapper
from django.db.models.functions import Coalesce

from api.models import Provider
from api.report.gcp.filter_collection import gcp_storage_conditional_filter_collection
from api.report.provider_map import ProviderMap
from reporting.provider.gcp.models import GCPComputeSummaryByAccountP
from reporting.provider.gcp.models import GCPComputeSummaryP
from reporting.provider.gcp.models import GCPCostEntryLineItemDailySummary
from reporting.provider.gcp.models import GCPCostSummaryByAccountP
from reporting.provider.gcp.models import GCPCostSummaryByProjectP
from reporting.provider.gcp.models import GCPCostSummaryByRegionP
from reporting.provider.gcp.models import GCPCostSummaryByServiceP
from reporting.provider.gcp.models import GCPCostSummaryP
from reporting.provider.gcp.models import GCPDatabaseSummaryP
from reporting.provider.gcp.models import GCPNetworkSummaryP
from reporting.provider.gcp.models import GCPStorageSummaryByAccountP
from reporting.provider.gcp.models import GCPStorageSummaryByProjectP
from reporting.provider.gcp.models import GCPStorageSummaryByRegionP
from reporting.provider.gcp.models import GCPStorageSummaryByServiceP
from reporting.provider.gcp.models import GCPStorageSummaryP


class GCPProviderMap(ProviderMap):
    """GCP Provider Map."""

    def __init__(self, provider, report_type, schema_name):
        """Constructor."""
        # group_by_annotations, filters, group_by_options, self.views
        self._mapping = [
            {
                "provider": Provider.PROVIDER_GCP,
                "annotations": {},  # Annotations that should always happen
                "group_by_annotations": {
                    "account": {"account": "account_id"},
                    "gcp_project": {"gcp_project": "project_id"},
                    "service": {"service": "service_alias"},
                },  # Annotations that should happen depending on group_by values
                "end_date": "usage_start",
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
                    "instance_type": {"field": "instance_type", "operation": "icontains"},
                },
                "group_by_options": ["account", "region", "service", "gcp_project"],
                "tag_column": "tags",
                "report_type": {
                    "costs": {
                        "aggregates": {
                            "infra_total": Sum(
                                (
                                    Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_credit": Sum(
                                Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "sup_credit": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                (
                                    Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_credit": Sum(
                                Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                        },
                        "aggregate_key": "unblended_cost",
                        "annotations": {
                            "infra_raw": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                (
                                    Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_credit": Sum(
                                Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "sup_credit": Sum(Value(0, output_field=DecimalField())),
                            "cost_raw": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Value(0, output_field=DecimalField()),
                            "cost_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                (
                                    Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_credit": Sum(
                                Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
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
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            )
                        },
                        "filter": [{}],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "sum_columns": ["cost_total", "infra_total", "sup_total"],
                        "default_ordering": {"cost_total": "desc"},
                    },
                    "instance_type": {
                        "aggregates": {
                            "infra_total": Sum(
                                (
                                    Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_credit": Sum(
                                Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "sup_credit": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                (
                                    Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_credit": Sum(
                                Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "usage": Sum("usage_amount"),
                        },
                        "aggregate_key": "usage_amount",
                        "annotations": {
                            "infra_total": Sum(
                                (
                                    Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_credit": Sum(
                                Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "sup_credit": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                (
                                    Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Value(0, output_field=DecimalField()),
                            "cost_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
                            "cost_credit": Sum(
                                Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "usage": Sum("usage_amount"),
                            "usage_units": Coalesce(Max("unit"), Value("hour")),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "delta_key": {"usage": Sum("usage_amount")},
                        "filter": [
                            {"field": "instance_type", "operation": "isnull", "parameter": False},
                            {"field": "unit", "operation": "exact", "parameter": "hour"},
                        ],
                        "group_by": ["instance_type"],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit",
                        "usage_units_fallback": "hour",
                        "sum_columns": ["usage", "cost_total", "sup_total", "infra_total"],
                        "default_ordering": {"usage": "desc"},
                        # COST-3043
                        # a default filter to use if querying a specific table. Filter generated in gcp_filter
                        "conditionals": {
                            GCPCostEntryLineItemDailySummary: {
                                "filter": [
                                    {
                                        "field": "sku_alias",
                                        "operation": "icontains",
                                        "parameter": "Instance Core running",
                                    },
                                ],
                            },
                        },
                    },
                    "storage": {
                        "aggregates": {
                            "infra_total": Sum(
                                (
                                    Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_credit": Sum(
                                Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "sup_credit": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                (
                                    Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_credit": Sum(
                                Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "usage": Sum("usage_amount"),
                        },
                        "aggregate_key": "usage_amount",
                        "annotations": {
                            "infra_raw": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                (
                                    Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_credit": Sum(
                                Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "sup_credit": Sum(Value(0, output_field=DecimalField())),
                            "cost_raw": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                (
                                    Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_credit": Sum(
                                Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
                            "usage": Sum("usage_amount"),
                            "usage_units": Coalesce(Max("unit"), Value("gibibyte month")),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "delta_key": {"usage": Sum("usage_amount")},
                        # Most of the storage cost was gibibyte month, however one was gibibyte.
                        "filter": [{"field": "unit", "operation": "exact", "parameter": "gibibyte month"}],
                        "conditionals": {
                            "conditionals": {
                                GCPCostEntryLineItemDailySummary: {
                                    "filter_collection": lambda: gcp_storage_conditional_filter_collection(
                                        schema_name
                                    ),
                                },
                            },
                        },
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
                "tables": {"query": GCPCostEntryLineItemDailySummary},
            }
        ]

        self.views = {
            "costs": {
                "default": GCPCostSummaryP,
                ("account",): GCPCostSummaryByAccountP,
                ("region",): GCPCostSummaryByRegionP,
                ("account", "region"): GCPCostSummaryByRegionP,
                ("service",): GCPCostSummaryByServiceP,
                ("account", "service"): GCPCostSummaryByServiceP,
                ("gcp_project",): GCPCostSummaryByProjectP,
                ("account", "gcp_project"): GCPCostSummaryByProjectP,
            },
            "instance_type": {"default": GCPComputeSummaryP, ("account",): GCPComputeSummaryByAccountP},
            "storage": {
                "default": GCPStorageSummaryP,
                ("account",): GCPStorageSummaryByAccountP,
                ("region",): GCPStorageSummaryByRegionP,
                ("account", "region"): GCPStorageSummaryByRegionP,
                ("service",): GCPStorageSummaryByServiceP,
                ("account", "service"): GCPStorageSummaryByServiceP,
                ("gcp_project",): GCPStorageSummaryByProjectP,
                ("account", "gcp_project"): GCPStorageSummaryByProjectP,
            },
            "database": {
                "default": GCPDatabaseSummaryP,
                ("service",): GCPDatabaseSummaryP,
                ("account", "service"): GCPDatabaseSummaryP,
                ("account",): GCPDatabaseSummaryP,
            },
            "network": {
                "default": GCPNetworkSummaryP,
                ("service",): GCPNetworkSummaryP,
                ("account", "service"): GCPNetworkSummaryP,
                ("account",): GCPNetworkSummaryP,
            },
        }
        # I needed a way to identify gcp in the parent class in queries.py so that
        # way we could filter off of invoice month instead of usage dates for
        # monthly time scope values.
        self.gcp_filters = True
        super().__init__(provider, report_type, schema_name)
