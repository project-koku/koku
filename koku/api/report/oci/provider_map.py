#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider Mapper for OCI Reports."""
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
from reporting.provider.oci.models import OCIComputeSummaryByAccountP
from reporting.provider.oci.models import OCIComputeSummaryP
from reporting.provider.oci.models import OCICostEntryLineItemDailySummary
from reporting.provider.oci.models import OCICostSummaryByAccountP
from reporting.provider.oci.models import OCICostSummaryByRegionP
from reporting.provider.oci.models import OCICostSummaryByServiceP
from reporting.provider.oci.models import OCICostSummaryP
from reporting.provider.oci.models import OCIDatabaseSummaryP
from reporting.provider.oci.models import OCINetworkSummaryP
from reporting.provider.oci.models import OCIStorageSummaryByAccountP
from reporting.provider.oci.models import OCIStorageSummaryP


CSV_FIELD_MAP = {"tenant": "id"}


class OCIProviderMap(ProviderMap):
    """OCI Provider Map."""

    def __init__(self, provider, report_type, cost_type):
        """Constructor."""
        self.markup_cost = "markup_cost"
        if cost_type != "cost":
            self.markup_cost = "markup_cost_" + cost_type.split("_")[0]
        self._mapping = [
            {
                "provider": Provider.PROVIDER_OCI,
                "annotations": {
                    "account": "payer_tenant_id",
                },
                "group_by_annotations": {
                    "account": {"tenant": "payer_tenant_id"},
                    "service": {"service": "product_service"},
                },  # Annotations that should happen depending on group_by values
                # This is to make sure that the date range generator uses usage_start for >= and <= comparisions
                "end_date": "usage_start",
                "filters": {
                    "account": {
                        "field": "payer_tenant_id",
                        "operation": "icontains",
                        "composition_key": "account_filter",
                    },
                    "service": {"field": "product_service", "operation": "icontains"},
                    "region": {"field": "region", "operation": "icontains"},
                    "instance_type": {"field": "instance_type", "operation": "icontains"},
                },
                "group_by_options": ["service", "account", "region"],
                "tag_column": "tags",
                "report_type": {
                    "costs": {
                        "aggregates": {
                            "infra_total": Sum(
                                Coalesce(F(cost_type), Value(0, output_field=DecimalField()))
                                + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(Coalesce(F(cost_type), Value(0, output_field=DecimalField()))),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(F(cost_type), Value(0, output_field=DecimalField()))
                                + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(Coalesce(F(cost_type), Value(0, output_field=DecimalField()))),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))),
                        },
                        "aggregate_key": cost_type,
                        "annotations": {
                            "infra_raw": Sum(Coalesce(F(cost_type), Value(0, output_field=DecimalField()))),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))),
                            "infra_total": Sum(
                                Coalesce(F(cost_type), Value(0, output_field=DecimalField()))
                                + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_raw": Sum(Coalesce(F(cost_type), Value(0, output_field=DecimalField()))),
                            "cost_usage": Value(0, output_field=DecimalField()),
                            "cost_markup": Sum(Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))),
                            "cost_total": Sum(
                                Coalesce(F(cost_type), Value(0, output_field=DecimalField()))
                                + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                            ),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "delta_key": {
                            # cost goes to cost_total
                            "cost_total": Sum(
                                ExpressionWrapper(
                                    Coalesce(F(cost_type), Value(0, output_field=DecimalField()))
                                    + F(self.markup_cost),
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
                    "instance_type": {
                        "aggregates": {
                            "infra_raw": Sum(Coalesce(F(cost_type), Value(0, output_field=DecimalField()))),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))),
                            "infra_total": Sum(
                                Coalesce(F(cost_type), Value(0, output_field=DecimalField()))
                                + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                            ),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(F(cost_type), Value(0, output_field=DecimalField()))
                                + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(Coalesce(F(cost_type), Value(0, output_field=DecimalField()))),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))),
                            "count": Sum(Value(0, output_field=DecimalField())),
                            "usage": Sum("usage_amount"),
                        },
                        "aggregate_key": "usage_amount",
                        "annotations": {
                            "infra_raw": Sum(Coalesce(F(cost_type), Value(0, output_field=DecimalField()))),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))),
                            "infra_total": Sum(
                                Coalesce(F(cost_type), Value(0, output_field=DecimalField()))
                                + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_raw": Sum(Coalesce(F(cost_type), Value(0, output_field=DecimalField()))),
                            "cost_usage": Value(0, output_field=DecimalField()),
                            "cost_markup": Sum(Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))),
                            "cost_total": Sum(
                                Coalesce(F(cost_type), Value(0, output_field=DecimalField()))
                                + Coalesce(F(self.markup_cost), Value(0, output_field=DecimalField()))
                            ),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "count": Max("resource_count"),
                            "count_units": Value("instances", output_field=CharField()),
                            "usage": Sum("usage_amount"),
                            "usage_units": Coalesce(Max("unit"), Value("Hrs")),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "delta_key": {"usage": Sum("usage_amount")},
                        "filter": [{"field": "instance_type", "operation": "isnull", "parameter": False}],
                        "group_by": ["instance_type"],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit",
                        "usage_units_fallback": "Hrs",
                        "count_units_fallback": "instances",
                        "sum_columns": ["usage", "cost_total", "infra_total", "sup_total", "count"],
                        "default_ordering": {"usage": "desc"},
                    },
                    "storage": {
                        "aggregates": {
                            "infra_total": Sum(
                                Coalesce(
                                    NullIf(F(cost_type), Value(0, output_field=DecimalField())),
                                    Coalesce("unblended_cost", Value(0, output_field=DecimalField())),
                                )
                                + Coalesce(
                                    NullIf(F(self.markup_cost), Value(0, output_field=DecimalField())),
                                    Coalesce("markup_cost", Value(0, output_field=DecimalField())),
                                )
                            ),
                            "infra_raw": Sum(
                                Coalesce(
                                    NullIf(F(cost_type), Value(0, output_field=DecimalField())),
                                    Coalesce("unblended_cost", Value(0, output_field=DecimalField())),
                                )
                            ),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(
                                    NullIf(F(self.markup_cost), Value(0, output_field=DecimalField())),
                                    Coalesce("markup_cost", Value(0, output_field=DecimalField())),
                                )
                            ),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(
                                    NullIf(F(cost_type), Value(0, output_field=DecimalField())),
                                    Coalesce("unblended_cost", Value(0, output_field=DecimalField())),
                                )
                                + Coalesce(
                                    NullIf(F(self.markup_cost), Value(0, output_field=DecimalField())),
                                    Coalesce("markup_cost", Value(0, output_field=DecimalField())),
                                )
                            ),
                            "cost_raw": Sum(
                                Coalesce(
                                    NullIf(F(cost_type), Value(0, output_field=DecimalField())),
                                    Coalesce("unblended_cost", Value(0, output_field=DecimalField())),
                                )
                            ),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(
                                    NullIf(F(self.markup_cost), Value(0, output_field=DecimalField())),
                                    Coalesce("markup_cost", Value(0, output_field=DecimalField())),
                                )
                            ),
                            "usage": Sum("usage_amount"),
                        },
                        "aggregate_key": "usage_amount",
                        "annotations": {
                            "infra_raw": Sum(
                                Coalesce(
                                    NullIf(F(cost_type), Value(0, output_field=DecimalField())),
                                    Coalesce("unblended_cost", Value(0, output_field=DecimalField())),
                                )
                            ),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(
                                Coalesce(
                                    NullIf(F(self.markup_cost), Value(0, output_field=DecimalField())),
                                    Coalesce("markup_cost", Value(0, output_field=DecimalField())),
                                )
                            ),
                            "infra_total": Sum(
                                Coalesce(
                                    NullIf(F(cost_type), Value(0, output_field=DecimalField())),
                                    Coalesce("unblended_cost", Value(0, output_field=DecimalField())),
                                )
                                + Coalesce(
                                    NullIf(F(self.markup_cost), Value(0, output_field=DecimalField())),
                                    Coalesce("markup_cost", Value(0, output_field=DecimalField())),
                                )
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_raw": Sum(
                                Coalesce(
                                    NullIf(F(cost_type), Value(0, output_field=DecimalField())),
                                    Coalesce("unblended_cost", Value(0, output_field=DecimalField())),
                                )
                            ),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(
                                    NullIf(F(self.markup_cost), Value(0, output_field=DecimalField())),
                                    Coalesce("markup_cost", Value(0, output_field=DecimalField())),
                                )
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    NullIf(F(cost_type), Value(0, output_field=DecimalField())),
                                    Coalesce("unblended_cost", Value(0, output_field=DecimalField())),
                                )
                                + Coalesce(
                                    NullIf(F(self.markup_cost), Value(0, output_field=DecimalField())),
                                    Coalesce("markup_cost", Value(0, output_field=DecimalField())),
                                )
                            ),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "usage": Sum("usage_amount"),
                            "usage_units": Coalesce(Max("unit"), Value("GB-Mo")),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "delta_key": {"usage": Sum("usage_amount")},
                        "filter": [
                            {"field": "unit", "operation": "exact", "parameter": "GB-Mo"},
                        ],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit",
                        "usage_units_fallback": "GB-Mo",
                        "sum_columns": ["usage", "cost_total", "sup_total", "infra_total"],
                        "default_ordering": {"usage": "desc"},
                    },
                    "tags": {"default_ordering": {"cost_total": "desc"}},
                },
                "start_date": "usage_start",
                "tables": {"query": OCICostEntryLineItemDailySummary},
            }
        ]

        self.views = {
            "costs": {
                "default": OCICostSummaryP,
                ("account",): OCICostSummaryByAccountP,
                ("region",): OCICostSummaryByRegionP,
                ("account", "region"): OCICostSummaryByRegionP,
                ("service",): OCICostSummaryByServiceP,
                ("account", "service"): OCICostSummaryByServiceP,
            },
            "instance_type": {
                "default": OCIComputeSummaryP,
                ("account",): OCIComputeSummaryByAccountP,
                ("instance_type",): OCIComputeSummaryP,
                ("account", "instance_type"): OCIComputeSummaryByAccountP,
            },
            "storage": {
                "default": OCIStorageSummaryP,
                ("account",): OCIStorageSummaryByAccountP,
            },
            "database": {
                "default": OCIDatabaseSummaryP,
                ("service",): OCIDatabaseSummaryP,
                ("account", "service"): OCIDatabaseSummaryP,
                ("account",): OCIDatabaseSummaryP,
            },
            "network": {
                "default": OCINetworkSummaryP,
                ("service",): OCINetworkSummaryP,
                ("account", "service"): OCINetworkSummaryP,
                ("account",): OCINetworkSummaryP,
            },
        }
        super().__init__(provider, report_type)
