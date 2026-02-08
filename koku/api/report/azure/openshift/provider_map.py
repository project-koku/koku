#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider Mapper for OCP on Azure Reports."""
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import CharField
from django.db.models import DecimalField
from django.db.models import ExpressionWrapper
from django.db.models import F
from django.db.models import Max
from django.db.models import Q
from django.db.models import Sum
from django.db.models import Value
from django.db.models.functions import Coalesce

from api.models import Provider
from api.report.provider_map import ProviderMap
from reporting.models import OCPAzureComputeSummaryP
from reporting.models import OCPAzureCostLineItemProjectDailySummaryP
from reporting.models import OCPAzureCostSummaryByAccountP
from reporting.models import OCPAzureCostSummaryByLocationP
from reporting.models import OCPAzureCostSummaryByServiceP
from reporting.models import OCPAzureCostSummaryP
from reporting.models import OCPAzureDatabaseSummaryP
from reporting.models import OCPAzureNetworkSummaryP
from reporting.models import OCPAzureStorageSummaryP


class OCPAzureProviderMap(ProviderMap):
    """OCP on Azure Provider Map."""

    def __init__(self, provider, report_type, schema_name):
        """Constructor."""
        self._mapping = [
            {
                "provider": Provider.OCP_AZURE,
                "alias": "subscription_name",
                "annotations": {"cluster": "cluster_id"},
                "end_date": "costentrybill__billing_period_start",
                "filters": {
                    "category": {"field": "cost_category__name", "operation": "icontains"},
                    "project": {"field": "namespace", "operation": "icontains"},
                    "cluster": [
                        {"field": "cluster_alias", "operation": "icontains", "composition_key": "cluster_filter"},
                        {"field": "cluster_id", "operation": "icontains", "composition_key": "cluster_filter"},
                    ],
                    "node": {"field": "node", "operation": "icontains"},
                    "subscription_guid": [
                        {"field": "subscription_guid", "operation": "icontains", "composition_key": "account_filter"},
                        {"field": "subscription_name", "operation": "icontains", "composition_key": "account_filter"},
                    ],
                    "service_name": {"field": "service_name", "operation": "icontains"},
                    "resource_location": {"field": "resource_location", "operation": "icontains"},
                    "instance_type": {"field": "instance_type", "operation": "icontains"},
                },
                "group_by_options": [
                    "cluster",  # ocp
                    "project",  # ocp
                    "node",  # ocp
                    "service_name",  # azure
                    "subscription_guid",  # azure
                    "resource_location",  # azure
                    "instance_type",  # azure
                ],
                "tag_column": "tags",
                "report_type": {
                    "costs": {
                        "aggregates": {
                            "infra_total": Sum(
                                (
                                    Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                (
                                    Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                        },
                        "annotations": {
                            # Cost is the first column in annotations so that it
                            # can reference the original database column 'markup_cost'
                            # If cost comes after the markup_cost annotaton, then
                            # Django will reference the annotated value, which is
                            # a Sum() and things will break trying to add
                            # a column with the sum of another column.
                            "cost_total": Sum(
                                (
                                    Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                (
                                    Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "infra_raw": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "cost_raw": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Value(0, output_field=DecimalField()),
                            "cost_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
                            "clusters": ArrayAgg(
                                Coalesce("cluster_alias", "cluster_id"), distinct=True, default=Value([])
                            ),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True, default=Value([])
                            ),
                        },
                        "delta_key": {
                            "cost_total": Sum(
                                (
                                    Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            )
                        },
                        "filter": [{}],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "sum_columns": ["cost_total", "sup_total", "infra_total"],
                        "default_ordering": {"cost_total": "desc"},
                    },
                    "storage": {
                        "aggregates": {
                            "infra_total": Sum(
                                (
                                    Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                (
                                    Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "usage": Sum(F("usage_quantity")),
                            "usage_units": Coalesce(
                                ExpressionWrapper(Max("unit_of_measure"), output_field=CharField()),
                                Value("GB-Mo", output_field=CharField()),
                            ),
                        },
                        "annotations": {
                            "infra_total": Sum(
                                (
                                    Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                (
                                    Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
                            "usage": Sum(F("usage_quantity")),
                            "usage_units": Coalesce(
                                ExpressionWrapper(Max("unit_of_measure"), output_field=CharField()),
                                Value("GB-Mo", output_field=CharField()),
                            ),
                            "clusters": ArrayAgg(
                                Coalesce("cluster_alias", "cluster_id"), distinct=True, default=Value([])
                            ),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True, default=Value([])
                            ),
                        },
                        "delta_key": {"usage": Sum("usage_quantity")},
                        "filter": [
                            {"field": "service_name", "operation": "icontains", "parameter": "Storage"},
                            {"field": "unit_of_measure", "operation": "exact", "parameter": "GB-Mo"},
                        ],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit_of_measure",
                        "usage_units_fallback": "GB-Mo",
                        "sum_columns": ["usage", "cost_total", "sup_total", "infra_total"],
                        "default_ordering": {"usage": "desc"},
                    },
                    "instance_type": {
                        "aggregates": {
                            "infra_total": Sum(
                                (
                                    Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                (
                                    Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "usage": Sum(F("usage_quantity")),
                            "usage_units": Coalesce(
                                ExpressionWrapper(Max("unit_of_measure"), output_field=CharField()),
                                Value("Hrs", output_field=CharField()),
                            ),
                        },
                        "aggregate_key": "usage_quantity",
                        "annotations": {
                            "infra_total": Sum(
                                (
                                    Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                (
                                    Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                    + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
                            "usage": Sum(F("usage_quantity")),
                            "usage_units": Coalesce(
                                ExpressionWrapper(Max("unit_of_measure"), output_field=CharField()),
                                Value("Hrs", output_field=CharField()),
                            ),
                            "clusters": ArrayAgg(
                                Coalesce("cluster_alias", "cluster_id"), distinct=True, default=Value([])
                            ),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True, default=Value([])
                            ),
                        },
                        "delta_key": {"usage": Sum("usage_quantity")},
                        "filter": [
                            {"field": "instance_type", "operation": "isnull", "parameter": False},
                            {"field": "unit_of_measure", "operation": "exact", "parameter": "Hrs"},
                        ],
                        "group_by": ["instance_type"],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit_of_measure",
                        "usage_units_fallback": "Hrs",
                        "sum_columns": ["usage", "cost_total", "sup_total", "infra_total"],
                        "default_ordering": {"usage": "desc"},
                    },
                    "tags": {"default_ordering": {"cost_total": "desc"}},
                },
                "start_date": "usage_start",
                "tables": {
                    "query": OCPAzureCostLineItemProjectDailySummaryP,
                    "total": OCPAzureCostLineItemProjectDailySummaryP,
                },
            }
        ]

        self.views = {
            "costs": {
                "default": OCPAzureCostSummaryP,
                ("subscription_guid",): OCPAzureCostSummaryByAccountP,
                ("service_name",): OCPAzureCostSummaryByServiceP,
                ("service_name", "subscription_guid"): OCPAzureCostSummaryByServiceP,
                ("resource_location",): OCPAzureCostSummaryByLocationP,
                ("resource_location", "subscription_guid"): OCPAzureCostSummaryByLocationP,
            },
            "instance_type": {
                "default": OCPAzureComputeSummaryP,
                ("instance_type",): OCPAzureComputeSummaryP,
                ("instance_type", "subscription_guid"): OCPAzureComputeSummaryP,
                ("subscription_guid",): OCPAzureComputeSummaryP,
            },
            "storage": {"default": OCPAzureStorageSummaryP, ("subscription_guid",): OCPAzureStorageSummaryP},
            "database": {
                "default": OCPAzureDatabaseSummaryP,
                ("service_name",): OCPAzureDatabaseSummaryP,
                ("service_name", "subscription_guid"): OCPAzureDatabaseSummaryP,
                ("subscription_guid",): OCPAzureDatabaseSummaryP,
            },
            "network": {
                "default": OCPAzureNetworkSummaryP,
                ("service_name",): OCPAzureNetworkSummaryP,
                ("service_name", "subscription_guid"): OCPAzureNetworkSummaryP,
                ("subscription_guid",): OCPAzureNetworkSummaryP,
            },
        }
        super().__init__(provider, report_type, schema_name)
