#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider Mapper for Azure Reports."""
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
from reporting.models import AzureComputeSummaryP
from reporting.models import AzureCostEntryLineItemDailySummary
from reporting.models import AzureCostSummaryByAccountP
from reporting.models import AzureCostSummaryByLocationP
from reporting.models import AzureCostSummaryByServiceP
from reporting.models import AzureCostSummaryP
from reporting.models import AzureDatabaseSummaryP
from reporting.models import AzureNetworkSummaryP
from reporting.models import AzureStorageSummaryP


class AzureProviderMap(ProviderMap):
    """Azure Provider Map."""

    def __init__(self, provider, report_type):
        """Constructor."""
        self._mapping = [
            {
                "provider": Provider.PROVIDER_AZURE,
                "alias": "subscription_guid",  # FIXME: probably wrong
                "annotations": {},
                "end_date": "costentrybill__billing_period_end",
                "filters": {
                    "subscription_guid": [
                        {"field": "subscription_guid", "operation": "icontains", "composition_key": "account_filter"}
                    ],
                    "service_name": {"field": "service_name", "operation": "icontains"},
                    "resource_location": {"field": "resource_location", "operation": "icontains"},
                    "instance_type": {"field": "instance_type", "operation": "icontains"},
                },
                "group_by_options": ["service_name", "subscription_guid", "resource_location", "instance_type"],
                "tag_column": "tags",
                "report_type": {
                    "costs": {
                        "aggregates": {
                            "infra_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("pretax_cost"),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("pretax_cost"),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                        },
                        "aggregate_key": "pretax_cost",
                        "annotations": {
                            "infra_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("pretax_cost"),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("pretax_cost"),
                            "cost_usage": Value(0, output_field=DecimalField()),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "delta_key": {
                            "cost_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
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
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("pretax_cost"),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("pretax_cost"),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "count": Sum(Value(0, output_field=DecimalField())),
                            "usage": Sum("usage_quantity"),
                        },
                        "aggregate_key": "usage_quantity",
                        "annotations": {
                            "infra_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("pretax_cost"),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("pretax_cost"),
                            "cost_usage": Value(0, output_field=DecimalField()),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "count": Max("instance_count"),
                            "count_units": Value("instance_types", output_field=CharField()),
                            "usage": Sum("usage_quantity"),
                            "usage_units": Coalesce(Max("unit_of_measure"), Value("Hrs")),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
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
                        "count_units_fallback": "instances",
                        "sum_columns": ["usage", "cost_total", "sup_total", "infra_total", "count"],
                        "default_ordering": {"usage": "desc"},
                    },
                    "storage": {
                        "aggregates": {
                            "infra_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("pretax_cost"),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("pretax_cost"),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "usage": Sum("usage_quantity"),
                        },
                        "aggregate_key": "usage_quantity",
                        "annotations": {
                            "infra_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("pretax_cost"),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("pretax_cost"),
                            "cost_usage": Value(0, output_field=DecimalField()),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "usage": Sum("usage_quantity"),
                            "usage_units": Coalesce(Max("unit_of_measure"), Value("GB-Mo")),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
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
                    "tags": {"default_ordering": {"cost_total": "desc"}},
                },
                "start_date": "costentrybill__billing_period_start",
                "tables": {"query": AzureCostEntryLineItemDailySummary},
            }
        ]

        self.views = {
            "costs": {
                "default": AzureCostSummaryP,
                ("subscription_guid",): AzureCostSummaryByAccountP,
                ("resource_location",): AzureCostSummaryByLocationP,
                ("resource_location", "subscription_guid"): AzureCostSummaryByLocationP,
                ("service_name",): AzureCostSummaryByServiceP,
                ("service_name", "subscription_guid"): AzureCostSummaryByServiceP,
            },
            "instance_type": {
                "default": AzureComputeSummaryP,
                ("instance_type",): AzureComputeSummaryP,
                ("instance_type", "subscription_guid"): AzureComputeSummaryP,
                ("subscription_guid",): AzureComputeSummaryP,
            },
            "storage": {"default": AzureStorageSummaryP, ("subscription_guid",): AzureStorageSummaryP},
            "database": {
                "default": AzureDatabaseSummaryP,
                ("service_name",): AzureDatabaseSummaryP,
                ("service_name", "subscription_guid"): AzureDatabaseSummaryP,
                ("subscription_guid",): AzureDatabaseSummaryP,
            },
            "network": {
                "default": AzureNetworkSummaryP,
                ("service_name",): AzureNetworkSummaryP,
                ("service_name", "subscription_guid"): AzureNetworkSummaryP,
                ("subscription_guid",): AzureNetworkSummaryP,
            },
        }
        super().__init__(provider, report_type)
