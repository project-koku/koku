#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider Mapper for GCP Reports."""
from django.contrib.postgres.aggregates import ArrayAgg
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
from reporting.provider.gcp.models import GCPComputeSummary
from reporting.provider.gcp.models import GCPComputeSummaryByAccount
from reporting.provider.gcp.models import GCPComputeSummaryByProject
from reporting.provider.gcp.models import GCPComputeSummaryByRegion
from reporting.provider.gcp.models import GCPComputeSummaryByService
from reporting.provider.gcp.models import GCPCostEntryLineItemDailySummary
from reporting.provider.gcp.models import GCPCostSummary
from reporting.provider.gcp.models import GCPCostSummaryByAccount
from reporting.provider.gcp.models import GCPCostSummaryByProject
from reporting.provider.gcp.models import GCPCostSummaryByRegion
from reporting.provider.gcp.models import GCPCostSummaryByService
from reporting.provider.gcp.models import GCPDatabaseSummary
from reporting.provider.gcp.models import GCPNetworkSummary
from reporting.provider.gcp.models import GCPStorageSummary
from reporting.provider.gcp.models import GCPStorageSummaryByAccount
from reporting.provider.gcp.models import GCPStorageSummaryByProject
from reporting.provider.gcp.models import GCPStorageSummaryByRegion
from reporting.provider.gcp.models import GCPStorageSummaryByService


class GCPProviderMap(ProviderMap):
    """GCP Provider Map."""

    def __init__(self, provider, report_type):
        """Constructor."""
        # TODO: COST-1986
        # group_by_annotations, filters, group_by_options, self.views
        self._mapping = [
            {
                "provider": Provider.PROVIDER_GCP,
                "annotations": {},  # Annotations that should always happen
                "group_by_annotations": {
                    "account": {"account": "account_id"},
                    "project": {"project": "project_id"},
                    "gcp_project": {"gcp_project": "project_id"},
                    "service": {"service": "service_alias"},
                },  # Annotations that should happen depending on group_by values
                "end_date": "usage_end",
                "filters": {
                    "account": {"field": "account_id", "operation": "icontains"},
                    "region": {"field": "region", "operation": "icontains"},
                    "service": [
                        {"field": "service_alias", "operation": "icontains", "composition_key": "service_filter"},
                        {"field": "service_id", "operation": "icontains", "composition_key": "service_filter"},
                    ],
                    "project": [
                        {"field": "project_name", "operation": "icontains", "composition_key": "project_filter"},
                        {"field": "project_id", "operation": "icontains", "composition_key": "project_filter"},
                    ],
                    "gcp_project": [
                        {"field": "project_name", "operation": "icontains", "composition_key": "project_filter"},
                        {"field": "project_id", "operation": "icontains", "composition_key": "project_filter"},
                    ],
                    "instance_type": {"field": "instance_type", "operation": "icontains"},
                },
                "group_by_options": ["account", "region", "service", "project", "gcp_project"],
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
                            "usage": Sum("usage_amount"),
                        },
                        "aggregate_key": "usage_amount",
                        "annotations": {
                            "infra_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("unblended_cost"),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "infra_credit": Sum(Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "sup_credit": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("unblended_cost"),
                            "cost_usage": Value(0, output_field=DecimalField()),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "cost_credit": Sum(Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))),
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
                            {"field": "sku_alias", "operation": "contains", "parameter": "Instance Core running"},
                        ],
                        "group_by": ["instance_type"],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit",
                        "usage_units_fallback": "hour",
                        "sum_columns": ["usage", "cost_total", "sup_total", "infra_total"],
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
                            "cost_credit": Sum(Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "usage": Sum("usage_amount"),
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
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_credit": Sum(Coalesce(F("credit_amount"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "usage": Sum("usage_amount"),
                            "usage_units": Coalesce(Max("unit"), Value("gibibyte month")),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "delta_key": {"usage": Sum("usage_amount")},
                        # Most of the storage cost was gibibyte month, however one was gibibyte.
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
                "tables": {"query": GCPCostEntryLineItemDailySummary},
            }
        ]

        self.views = {
            "costs": {
                "default": GCPCostSummary,
                ("account",): GCPCostSummaryByAccount,
                ("region",): GCPCostSummaryByRegion,
                ("account", "region"): GCPCostSummaryByRegion,
                ("service",): GCPCostSummaryByService,
                ("account", "service"): GCPCostSummaryByService,
                ("project",): GCPCostSummaryByProject,
                ("account", "project"): GCPCostSummaryByProject,
                ("gcp_project",): GCPCostSummaryByProject,
                ("account", "gcp_project"): GCPCostSummaryByProject,
                # COST-1981, COST-1986 Forecast stop gap
                ("gcp_project", "project"): GCPCostSummaryByProject,
                ("account", "gcp_project", "project"): GCPCostSummaryByProject,
            },
            "instance-type": {
                "default": GCPComputeSummary,
                ("account",): GCPComputeSummaryByAccount,
                ("region",): GCPComputeSummaryByRegion,
                ("account", "region"): GCPComputeSummaryByRegion,
                ("service",): GCPComputeSummaryByService,
                ("account", "service"): GCPComputeSummaryByService,
                ("project",): GCPComputeSummaryByProject,
                ("account", "project"): GCPComputeSummaryByProject,
                ("gcp_project",): GCPComputeSummaryByProject,
                ("account", "gcp_project"): GCPComputeSummaryByProject,
                # COST-1981, COST-1986 Forecast stop gap
                ("gcp_project", "project"): GCPComputeSummaryByProject,
                ("account", "gcp_project", "project"): GCPComputeSummaryByProject,
            },
            "storage": {
                "default": GCPStorageSummary,
                ("account",): GCPStorageSummaryByAccount,
                ("region",): GCPStorageSummaryByRegion,
                ("account", "region"): GCPStorageSummaryByRegion,
                ("service",): GCPStorageSummaryByService,
                ("account", "service"): GCPStorageSummaryByService,
                ("project",): GCPStorageSummaryByProject,
                ("account", "project"): GCPStorageSummaryByProject,
                ("gcp_project",): GCPStorageSummaryByProject,
                ("account", "gcp_project"): GCPStorageSummaryByProject,
                # COST-1981, COST-1986 Forecast stop gap
                ("gcp_project", "project"): GCPStorageSummaryByProject,
                ("account", "gcp_project", "project"): GCPStorageSummaryByProject,
            },
            "database": {
                "default": GCPDatabaseSummary,
                ("service",): GCPDatabaseSummary,
                ("account", "service"): GCPDatabaseSummary,
                ("account",): GCPDatabaseSummary,
            },
            "network": {
                "default": GCPNetworkSummary,
                ("service",): GCPNetworkSummary,
                ("account", "service"): GCPNetworkSummary,
                ("account",): GCPNetworkSummary,
            },
        }
        # I needed a way to identify gcp in the parent class in queries.py so that
        # way we could filter off of invoice month instead of usage dates for
        # monthly time scope values.
        self.gcp_filters = True
        super().__init__(provider, report_type)
