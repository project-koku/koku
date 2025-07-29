#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider Mapper for AWS Reports."""
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
from django.db.models.functions.comparison import NullIf

from api.models import Provider
from api.report.provider_map import ProviderMap
from reporting.provider.aws.models import AWSComputeSummaryByAccountP
from reporting.provider.aws.models import AWSComputeSummaryP
from reporting.provider.aws.models import AWSCostEntryLineItemDailySummary
from reporting.provider.aws.models import AWSCostEntryLineItemSummaryByEC2ComputeP
from reporting.provider.aws.models import AWSCostSummaryByAccountP
from reporting.provider.aws.models import AWSCostSummaryByRegionP
from reporting.provider.aws.models import AWSCostSummaryByServiceP
from reporting.provider.aws.models import AWSCostSummaryP
from reporting.provider.aws.models import AWSDatabaseSummaryP
from reporting.provider.aws.models import AWSNetworkSummaryP
from reporting.provider.aws.models import AWSStorageSummaryByAccountP
from reporting.provider.aws.models import AWSStorageSummaryP

CSV_FIELD_MAP = {"account": "id", "account_alias": "alias"}


class AWSProviderMap(ProviderMap):
    """AWS Provider Map."""

    def __init__(self, provider, report_type, schema_name, cost_type, markup_cost="markup_cost"):
        """Constructor."""
        self.cost_type = cost_type
        self.markup_cost = markup_cost
        self._mapping = [
            {
                "provider": Provider.PROVIDER_AWS,
                "alias": "account_alias__account_alias",
                "annotations": {
                    "account": "usage_account_id",
                    "service": "product_code",
                    "az": "availability_zone",
                    "org_unit_id": "organizational_unit__org_unit_id",
                    "org_unit_single_level": "organizational_unit__org_unit_id",
                },
                # This is to make sure that the date range generator uses usage_start for >= and <= comparisions
                "end_date": "usage_start",
                "filters": {
                    "account": [
                        {
                            "field": "account_alias__account_alias",
                            "operation": "icontains",
                            "composition_key": "account_filter",
                        },
                        {"field": "usage_account_id", "operation": "icontains", "composition_key": "account_filter"},
                    ],
                    "service": {"field": "product_code", "operation": "icontains"},
                    "az": {"field": "availability_zone", "operation": "icontains"},
                    "region": {"field": "region", "operation": "icontains"},
                    "product_family": {"field": "product_family", "operation": "icontains"},
                    "org_unit_id": {"field": "organizational_unit__org_unit_path", "operation": "icontains"},
                    "org_unit_single_level": {"field": "organizational_unit__org_unit_id", "operation": "icontains"},
                    "instance_type": {"field": "instance_type", "operation": "icontains"},
                    "operating_system": {"field": "operating_system", "operation": "icontains"},
                    "instance": [
                        {"field": "instance_name", "operation": "icontains", "composition_key": "instance_filter"},
                        {"field": "resource_id", "operation": "icontains", "composition_key": "instance_filter"},
                    ],
                },
                "group_by_options": ["service", "account", "region", "az", "product_family", "org_unit_id"],
                "tag_column": "tags",
                "aws_category_column": "cost_category",
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
                        "aggregate_key": self.cost_type,
                        "annotations": {
                            "infra_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Value(0, output_field=DecimalField()),
                            "cost_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
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
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + F(self.markup_cost),
                                    output_field=DecimalField(),
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            )
                        },
                        "filter": [{}],
                        "cost_units_key": "currency_code",
                        "cost_units_fallback": "USD",
                        "sum_columns": ["cost_total", "infra_total", "sup_total"],
                        "default_ordering": {"cost_total": "desc"},
                    },
                    "instance_type": {
                        "aggregates": {
                            "infra_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
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
                            "usage": Sum("usage_amount"),
                        },
                        "aggregate_key": "usage_amount",
                        "annotations": {
                            "infra_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Value(0, output_field=DecimalField()),
                            "cost_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
                            "usage": Sum("usage_amount"),
                            "usage_units": Coalesce(Max("unit"), Value("Hrs")),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "delta_key": {"usage": Sum("usage_amount")},
                        "filter": [{"field": "instance_type", "operation": "isnull", "parameter": False}],
                        "group_by": ["instance_type"],
                        "cost_units_key": "currency_code",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit",
                        "usage_units_fallback": "Hrs",
                        "sum_columns": ["usage", "cost_total", "infra_total", "sup_total"],
                        "default_ordering": {"usage": "desc"},
                    },
                    "ec2_compute": {
                        "aggregates": {
                            "infra_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
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
                            "usage": Sum("usage_amount"),
                        },
                        "aggregate_key": "usage_amount",
                        "annotations": {
                            "infra_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_raw": Sum(
                                Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Value(0, output_field=DecimalField()),
                            "cost_markup": Sum(
                                Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                (
                                    Coalesce(F(self.cost_type), Value(0, output_field=DecimalField()))
                                    + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
                            "usage": Sum("usage_amount"),
                            "usage_units": Coalesce(Max("unit"), Value("Hrs")),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                            "account_alias": Coalesce(Max("account_alias__account_alias"), Max("usage_account_id")),
                            "account": Max("usage_account_id"),
                            "instance_name": Coalesce(Max("instance_name"), Max("resource_id")),
                            "instance_type": Max("instance_type"),
                            "operating_system": Max("operating_system"),
                            "region": Max("region"),
                            "vcpu": Max("vcpu"),
                            "memory": Max("memory"),
                            "tags": ArrayAgg(F("tags")),
                        },
                        "filter": [{}],
                        "group_by": ["resource_id"],
                        "cost_units_key": "currency_code",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit",
                        "usage_units_fallback": "Hrs",
                        "sum_columns": ["usage", "cost_total", "infra_total", "sup_total"],
                        "default_ordering": {"resource_id": "desc"},
                        "tables": {"query": AWSCostEntryLineItemSummaryByEC2ComputeP},
                    },
                    "storage": {
                        "aggregates": {
                            "infra_total": Sum(
                                (
                                    Coalesce(
                                        NullIf(F(self.cost_type), Value(0, output_field=DecimalField())),
                                        Coalesce("unblended_cost", Value(0, output_field=DecimalField())),
                                    )
                                    + Coalesce(
                                        NullIf(F(self.markup_cost), Value(0, output_field=DecimalField())),
                                        Coalesce("markup_cost", Value(0, output_field=DecimalField())),
                                    )
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(
                                    NullIf(F(self.cost_type), Value(0, output_field=DecimalField())),
                                    Coalesce("unblended_cost", Value(0, output_field=DecimalField())),
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(
                                    NullIf(F(self.markup_cost), Value(0, output_field=DecimalField())),
                                    Coalesce("markup_cost", Value(0, output_field=DecimalField())),
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                (
                                    Coalesce(
                                        NullIf(F(self.cost_type), Value(0, output_field=DecimalField())),
                                        Coalesce("unblended_cost", Value(0, output_field=DecimalField())),
                                    )
                                    + Coalesce(
                                        NullIf(F(self.markup_cost), Value(0, output_field=DecimalField())),
                                        Coalesce("markup_cost", Value(0, output_field=DecimalField())),
                                    )
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(
                                    NullIf(F(self.cost_type), Value(0, output_field=DecimalField())),
                                    Coalesce("unblended_cost", Value(0, output_field=DecimalField())),
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(
                                    NullIf(F(self.markup_cost), Value(0, output_field=DecimalField())),
                                    Coalesce("markup_cost", Value(0, output_field=DecimalField())),
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "usage": Sum("usage_amount"),
                        },
                        "aggregate_key": "usage_amount",
                        "annotations": {
                            "infra_raw": Sum(
                                Coalesce(
                                    NullIf(F(self.cost_type), Value(0, output_field=DecimalField())),
                                    Coalesce("unblended_cost", Value(0, output_field=DecimalField())),
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(
                                Coalesce(
                                    NullIf(F(self.markup_cost), Value(0, output_field=DecimalField())),
                                    Coalesce("markup_cost", Value(0, output_field=DecimalField())),
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                (
                                    Coalesce(
                                        NullIf(F(self.cost_type), Value(0, output_field=DecimalField())),
                                        Coalesce("unblended_cost", Value(0, output_field=DecimalField())),
                                    )
                                    + Coalesce(
                                        NullIf(F(self.markup_cost), Value(0, output_field=DecimalField())),
                                        Coalesce("markup_cost", Value(0, output_field=DecimalField())),
                                    )
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_raw": Sum(
                                Coalesce(
                                    NullIf(F(self.cost_type), Value(0, output_field=DecimalField())),
                                    Coalesce("unblended_cost", Value(0, output_field=DecimalField())),
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(
                                    NullIf(F(self.markup_cost), Value(0, output_field=DecimalField())),
                                    Coalesce("markup_cost", Value(0, output_field=DecimalField())),
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                (
                                    Coalesce(
                                        NullIf(F(self.cost_type), Value(0, output_field=DecimalField())),
                                        Coalesce("unblended_cost", Value(0, output_field=DecimalField())),
                                    )
                                    + Coalesce(
                                        NullIf(F(self.markup_cost), Value(0, output_field=DecimalField())),
                                        Coalesce("markup_cost", Value(0, output_field=DecimalField())),
                                    )
                                )
                                * Coalesce("exchange_rate", Value(1, output_field=DecimalField()))
                            ),
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
                            "usage": Sum("usage_amount"),
                            "usage_units": Coalesce(Max("unit"), Value("GB-Mo")),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "delta_key": {"usage": Sum("usage_amount")},
                        "filter": [
                            {"field": "product_family", "operation": "icontains", "parameter": "Storage"},
                            {"field": "unit", "operation": "exact", "parameter": "GB-Mo"},
                        ],
                        "cost_units_key": "currency_code",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit",
                        "usage_units_fallback": "GB-Mo",
                        "sum_columns": ["usage", "cost_total", "sup_total", "infra_total"],
                        "default_ordering": {"usage": "desc"},
                    },
                    "tags": {"default_ordering": {"cost_total": "desc"}},
                },
                "start_date": "usage_start",
                "tables": {"query": AWSCostEntryLineItemDailySummary},
            }
        ]

        self.views = {
            "costs": {
                "default": AWSCostSummaryP,
                ("account",): AWSCostSummaryByAccountP,
                ("region",): AWSCostSummaryByRegionP,
                ("account", "region"): AWSCostSummaryByRegionP,
                ("service",): AWSCostSummaryByServiceP,
                ("account", "service"): AWSCostSummaryByServiceP,
                ("product_family",): AWSCostSummaryByServiceP,
                ("account", "product_family"): AWSCostSummaryByServiceP,
                ("account", "org_unit_id"): AWSCostSummaryByAccountP,
                ("org_unit_id",): AWSCostSummaryByAccountP,
                ("org_unit_single_level",): AWSCostSummaryByAccountP,
                ("account", "org_unit_single_level"): AWSCostSummaryByAccountP,
            },
            "instance_type": {
                "default": AWSComputeSummaryP,
                ("account",): AWSComputeSummaryByAccountP,
                ("instance_type",): AWSComputeSummaryP,
                ("account", "instance_type"): AWSComputeSummaryByAccountP,
                ("account", "org_unit_id"): AWSComputeSummaryByAccountP,
                ("org_unit_id",): AWSComputeSummaryByAccountP,
            },
            "ec2_compute": {
                "default": AWSCostEntryLineItemSummaryByEC2ComputeP,
            },
            "storage": {
                "default": AWSStorageSummaryP,
                ("account",): AWSStorageSummaryByAccountP,
                ("account", "org_unit_id"): AWSStorageSummaryByAccountP,
                ("org_unit_id",): AWSStorageSummaryByAccountP,
            },
            "database": {
                "default": AWSDatabaseSummaryP,
                ("service",): AWSDatabaseSummaryP,
                ("account", "service"): AWSDatabaseSummaryP,
                ("account",): AWSDatabaseSummaryP,
            },
            "network": {
                "default": AWSNetworkSummaryP,
                ("service",): AWSNetworkSummaryP,
                ("account", "service"): AWSNetworkSummaryP,
                ("account",): AWSNetworkSummaryP,
            },
        }
        super().__init__(provider, report_type, schema_name)

    @property
    def aws_category_column(self):
        return self.provider_map.get("aws_category_column")
