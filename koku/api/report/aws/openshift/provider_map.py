#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider Mapper for OCP on AWS Reports."""
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
from reporting.models import OCPAWSCostLineItemProjectDailySummaryP
from reporting.provider.aws.openshift.models import OCPAWSComputeSummaryP
from reporting.provider.aws.openshift.models import OCPAWSCostSummaryByAccountP
from reporting.provider.aws.openshift.models import OCPAWSCostSummaryByRegionP
from reporting.provider.aws.openshift.models import OCPAWSCostSummaryByServiceP
from reporting.provider.aws.openshift.models import OCPAWSCostSummaryP
from reporting.provider.aws.openshift.models import OCPAWSDatabaseSummaryP
from reporting.provider.aws.openshift.models import OCPAWSNetworkSummaryP
from reporting.provider.aws.openshift.models import OCPAWSStorageSummaryP


class OCPAWSProviderMap(ProviderMap):
    """OCP on AWS Provider Map."""

    def __init__(self, provider, report_type, schema_name, cost_type, markup_cost="markup_cost"):
        """Constructor."""
        self.cost_type = cost_type
        self.markup_cost = markup_cost
        self._mapping = [
            {
                "provider": Provider.OCP_AWS,
                "alias": "account_alias__account_alias",
                "annotations": {
                    "cluster": "cluster_id",
                    "project": "namespace",
                    "account": "usage_account_id",
                    "service": "product_code",
                    "az": "availability_zone",
                },
                "end_date": "usage_start",
                "filters": {
                    "category": {"field": "cost_category__name", "operation": "icontains"},
                    "project": {"field": "namespace", "operation": "icontains"},
                    "cluster": [
                        {"field": "cluster_alias", "operation": "icontains", "composition_key": "cluster_filter"},
                        {"field": "cluster_id", "operation": "icontains", "composition_key": "cluster_filter"},
                    ],
                    "node": {"field": "node", "operation": "icontains"},
                    "account": [
                        {
                            "field": "account_alias__account_alias",
                            "operation": "icontains",
                            "composition_key": "account_filter",
                        },
                        {"field": "usage_account_id", "operation": "icontains", "composition_key": "account_filter"},
                    ],
                    "service": {"field": "product_code", "operation": "icontains"},
                    "product_family": {"field": "product_family", "operation": "icontains"},
                    "az": {"field": "availability_zone", "operation": "icontains"},
                    "region": {"field": "region", "operation": "icontains"},
                    "instance_type": {"field": "instance_type", "operation": "icontains"},
                },
                "group_by_options": ["account", "service", "region", "cluster", "project", "node", "product_family"],
                "tag_column": "tags",
                "aws_category_column": "aws_cost_category",
                "report_type": {
                    "costs": {
                        "aggregates": {
                            "infra_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                        },
                        "annotations": {
                            "infra_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Value(0, output_field=DecimalField()),
                            "cost_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
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
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            )
                        },
                        "filter": [{}],
                        "cost_units_key": "currency_code",
                        "cost_units_fallback": "USD",
                        "sum_columns": ["cost_total", "sup_total", "infra_total"],
                        "default_ordering": {"cost_total": "desc"},
                    },
                    "storage": {
                        "aggregates": {
                            "infra_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "usage": Sum(Coalesce(F("usage_amount"), Value(0, output_field=DecimalField()))),
                            "usage_units": Coalesce(Max("unit"), Value("GB-Mo")),
                        },
                        "annotations": {
                            "infra_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
                            "usage": Sum(Coalesce(F("usage_amount"), Value(0, output_field=DecimalField()))),
                            "usage_units": Coalesce(Max("unit"), Value("GB-Mo")),
                            "clusters": ArrayAgg(
                                Coalesce("cluster_alias", "cluster_id"), distinct=True, default=Value([])
                            ),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True, default=Value([])
                            ),
                        },
                        "delta_key": {"usage": Sum("usage_amount")},
                        "filter": [{"field": "product_family", "operation": "icontains", "parameter": "Storage"}],
                        "cost_units_key": "currency_code",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit",
                        "usage_units_fallback": "GB-Mo",
                        "sum_columns": ["usage", "cost_total", "sup_total", "infra_total"],
                        "default_ordering": {"usage": "desc"},
                    },
                    "instance_type": {
                        "aggregates": {
                            "infra_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "usage": Sum(Coalesce(F("usage_amount"), Value(0, output_field=DecimalField()))),
                            "usage_units": Coalesce(Max("unit"), Value("GB-Mo")),
                        },
                        "aggregate_key": "usage_amount",
                        "annotations": {
                            "infra_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
                            "usage": Sum(Coalesce(F("usage_amount"), Value(0, output_field=DecimalField()))),
                            "usage_units": Coalesce(Max("unit"), Value("Hrs")),
                            "clusters": ArrayAgg(
                                Coalesce("cluster_alias", "cluster_id"), distinct=True, default=Value([])
                            ),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True, default=Value([])
                            ),
                        },
                        "delta_key": {"usage": Sum("usage_amount")},
                        "filter": [{"field": "instance_type", "operation": "isnull", "parameter": False}],
                        "group_by": ["instance_type"],
                        "cost_units_key": "currency_code",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit",
                        "usage_units_fallback": "Hrs",
                        "sum_columns": ["usage", "cost_total", "sup_total", "infra_total"],
                        "default_ordering": {"usage": "desc"},
                    },
                    "tags": {"default_ordering": {"cost_total": "desc"}},
                },
                "start_date": "usage_start",
                "tables": {
                    "query": OCPAWSCostLineItemProjectDailySummaryP,
                    "total": OCPAWSCostLineItemProjectDailySummaryP,
                },
            }
        ]

        self.views = {
            "costs": {
                "default": OCPAWSCostSummaryP,
                ("account",): OCPAWSCostSummaryByAccountP,
                ("service",): OCPAWSCostSummaryByServiceP,
                ("account", "service"): OCPAWSCostSummaryByServiceP,
                ("region",): OCPAWSCostSummaryByRegionP,
                ("account", "region"): OCPAWSCostSummaryByRegionP,
            },
            "instance_type": {
                "default": OCPAWSComputeSummaryP,
                ("instance_type",): OCPAWSComputeSummaryP,
                ("account", "instance_type"): OCPAWSComputeSummaryP,
                ("account",): OCPAWSComputeSummaryP,
            },
            "storage": {"default": OCPAWSStorageSummaryP, ("account",): OCPAWSStorageSummaryP},
            "database": {
                "default": OCPAWSDatabaseSummaryP,
                ("service",): OCPAWSDatabaseSummaryP,
                ("account", "service"): OCPAWSDatabaseSummaryP,
                ("account",): OCPAWSDatabaseSummaryP,
            },
            "network": {
                "default": OCPAWSNetworkSummaryP,
                ("service",): OCPAWSNetworkSummaryP,
                ("account", "service"): OCPAWSNetworkSummaryP,
                ("account",): OCPAWSNetworkSummaryP,
            },
        }
        super().__init__(provider, report_type, schema_name)

    @property
    def aws_category_column(self):
        return self.provider_map.get("aws_category_column")
