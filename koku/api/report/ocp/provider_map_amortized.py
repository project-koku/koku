#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider Mapper for OCP Reports."""
from functools import cached_property

from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import Case
from django.db.models import CharField
from django.db.models import DecimalField
from django.db.models import F
from django.db.models import Max
from django.db.models import Q
from django.db.models import Sum
from django.db.models import Value
from django.db.models import When
from django.db.models.functions import Coalesce

from api.models import Provider
from api.report.provider_map import ProviderMap
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

    def __cost_model_cost(self, cost_model_rate_type=None):
        """Return ORM term for cost model cost"""
        if cost_model_rate_type:
            return Sum(
                Case(
                    When(
                        cost_model_rate_type=cost_model_rate_type,
                        then=Coalesce(F("cost_model_cpu_cost"), Value(0, output_field=DecimalField()))
                        + Coalesce(F("cost_model_memory_cost"), Value(0, output_field=DecimalField()))
                        + Coalesce(F("cost_model_volume_cost"), Value(0, output_field=DecimalField())),
                    ),
                    default=Value(0, output_field=DecimalField()),
                )
                * Coalesce("exchange_rate", Value(1, output_field=DecimalField())),
            )
        else:
            return Sum(
                (
                    Coalesce(F("cost_model_cpu_cost"), Value(0, output_field=DecimalField()))
                    + Coalesce(F("cost_model_memory_cost"), Value(0, output_field=DecimalField()))
                    + Coalesce(F("cost_model_volume_cost"), Value(0, output_field=DecimalField()))
                )
                * Coalesce("exchange_rate", Value(1, output_field=DecimalField())),
            )

    def __cost_model_cpu_cost(self, cost_model_rate_type=None):
        """Return ORM term for cost model cost"""
        if cost_model_rate_type:
            return Sum(
                Case(
                    When(
                        cost_model_rate_type=cost_model_rate_type,
                        then=Coalesce(F("cost_model_cpu_cost"), Value(0, output_field=DecimalField())),
                    ),
                    default=Value(0, output_field=DecimalField()),
                )
                * Coalesce("exchange_rate", Value(1, output_field=DecimalField())),
            )
        else:
            return Sum(
                Coalesce(F("cost_model_cpu_cost"), Value(0, output_field=DecimalField()))
                * Coalesce("exchange_rate", Value(1, output_field=DecimalField())),
            )

    def __cost_model_memory_cost(self, cost_model_rate_type=None):
        """Return ORM term for cost model cost"""
        if cost_model_rate_type:
            return Sum(
                Case(
                    When(
                        cost_model_rate_type=cost_model_rate_type,
                        then=Coalesce(F("cost_model_memory_cost"), Value(0, output_field=DecimalField())),
                    ),
                    default=Value(0, output_field=DecimalField()),
                )
                * Coalesce("exchange_rate", Value(1, output_field=DecimalField())),
            )
        else:
            return Sum(
                Coalesce(F("cost_model_memory_cost"), Value(0, output_field=DecimalField()))
                * Coalesce("exchange_rate", Value(1, output_field=DecimalField())),
            )

    def __cost_model_volume_cost(self, cost_model_rate_type=None):
        """Return ORM term for cost model cost"""
        if cost_model_rate_type:
            return Sum(
                Case(
                    When(
                        cost_model_rate_type=cost_model_rate_type,
                        then=Coalesce(F("cost_model_volume_cost"), Value(0, output_field=DecimalField())),
                    ),
                    default=Value(0, output_field=DecimalField()),
                )
                * Coalesce("exchange_rate", Value(1, output_field=DecimalField())),
            )
        else:
            return Sum(
                Coalesce(F("cost_model_volume_cost"), Value(0, output_field=DecimalField()))
                * Coalesce("exchange_rate", Value(1, output_field=DecimalField())),
            )

    def __init__(self, provider, report_type):
        """Constructor."""
        self._mapping = [
            {
                "provider": Provider.PROVIDER_OCP,
                "annotations": {"cluster": "cluster_id"},
                "end_date": "usage_start",
                "filters": {
                    "category": {"field": "cost_category__name", "operation": "icontains"},
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
                            "sup_usage": self.cost_model_supplementary_cost,
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": self.cost_model_supplementary_cost,
                            "infra_raw": self.cloud_infrastructure_cost,
                            "infra_usage": self.cost_model_infrastructure_cost,
                            "infra_markup": self.markup_cost,
                            "infra_total": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_infrastructure_cost,
                            "cost_raw": self.cloud_infrastructure_cost,
                            "cost_usage": self.cost_model_cost,
                            "cost_markup": self.markup_cost,
                            "cost_total": self.cloud_infrastructure_cost + self.markup_cost + self.cost_model_cost,
                        },
                        "default_ordering": {"cost_total": "desc"},
                        "annotations": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": self.cost_model_supplementary_cost,
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": self.cost_model_supplementary_cost,
                            "infra_raw": self.cloud_infrastructure_cost,
                            "infra_usage": self.cost_model_infrastructure_cost,
                            "infra_markup": self.markup_cost,
                            "infra_total": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_infrastructure_cost,
                            "cost_raw": self.cloud_infrastructure_cost,
                            "cost_usage": self.cost_model_cost,
                            "cost_markup": self.markup_cost,
                            "cost_total": self.cloud_infrastructure_cost + self.markup_cost + self.cost_model_cost,
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "capacity_aggregate": {},
                        "delta_key": {
                            "cost_total": self.cloud_infrastructure_cost + self.markup_cost + self.cost_model_cost,
                        },
                        "filter": [{}],
                        "cost_units_key": "raw_currency",
                        "sum_columns": ["cost_total", "infra_total", "sup_total"],
                    },
                    "costs_by_project": {
                        "tables": {"query": OCPUsageLineItemDailySummary},
                        "aggregates": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": self.cost_model_supplementary_cost,
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": self.cost_model_supplementary_cost,
                            "infra_raw": self.cloud_infrastructure_cost_by_project,
                            "infra_usage": self.cost_model_infrastructure_cost,
                            "infra_markup": self.markup_cost_by_project,
                            "infra_total": self.cloud_infrastructure_cost_by_project
                            + self.markup_cost_by_project
                            + self.cost_model_infrastructure_cost,
                            "cost_raw": self.cloud_infrastructure_cost_by_project,
                            "cost_usage": self.cost_model_cost,
                            "cost_markup": self.markup_cost_by_project,
                            "cost_total": self.cloud_infrastructure_cost_by_project
                            + self.markup_cost_by_project
                            + self.cost_model_cost,
                        },
                        "default_ordering": {"cost_total": "desc"},
                        "annotations": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": self.cost_model_supplementary_cost,
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": self.cost_model_supplementary_cost,
                            "infra_raw": self.cloud_infrastructure_cost_by_project,
                            "infra_usage": self.cost_model_infrastructure_cost,
                            "infra_markup": self.markup_cost_by_project,
                            "infra_total": self.cloud_infrastructure_cost_by_project
                            + self.markup_cost_by_project
                            + self.cost_model_infrastructure_cost,
                            "cost_raw": self.cloud_infrastructure_cost_by_project,
                            "cost_usage": self.cost_model_cost,
                            "cost_markup": self.markup_cost_by_project,
                            "cost_total": self.cloud_infrastructure_cost_by_project
                            + self.markup_cost_by_project
                            + self.cost_model_cost,
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "capacity_aggregate": {},
                        "delta_key": {
                            "cost_total": self.cloud_infrastructure_cost_by_project
                            + self.markup_cost_by_project
                            + self.cost_model_cost,
                        },
                        "filter": [{}],
                        "cost_units_key": "raw_currency",
                        "sum_columns": ["cost_total", "infra_total", "sup_total"],
                    },
                    "cpu": {
                        "aggregates": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": self.cost_model_cpu_supplementary_cost,
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": self.cost_model_cpu_supplementary_cost,
                            "infra_raw": self.cloud_infrastructure_cost,
                            "infra_usage": self.cost_model_cpu_infrastructure_cost,
                            "infra_markup": self.markup_cost,
                            "infra_total": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_cpu_infrastructure_cost,
                            "cost_raw": self.cloud_infrastructure_cost,
                            "cost_usage": self.cost_model_cpu_cost,
                            "cost_markup": self.markup_cost,
                            "cost_total": self.cloud_infrastructure_cost + self.markup_cost + self.cost_model_cpu_cost,
                            "usage": Sum("pod_usage_cpu_core_hours"),
                            "request": Sum("pod_request_cpu_core_hours"),
                            "limit": Sum("pod_limit_cpu_core_hours"),
                        },
                        "capacity_aggregate": {"capacity": Max("cluster_capacity_cpu_core_hours")},
                        "default_ordering": {"usage": "desc"},
                        "annotations": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": self.cost_model_cpu_supplementary_cost,
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": self.cost_model_cpu_supplementary_cost,
                            "infra_raw": self.cloud_infrastructure_cost,
                            "infra_usage": self.cost_model_cpu_infrastructure_cost,
                            "infra_markup": self.markup_cost,
                            "infra_total": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_cpu_infrastructure_cost,
                            "cost_raw": self.cloud_infrastructure_cost,
                            "cost_usage": self.cost_model_cpu_cost,
                            "cost_markup": self.markup_cost,
                            "cost_total": self.cloud_infrastructure_cost + self.markup_cost + self.cost_model_cpu_cost,
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
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
                            "cost_total": self.cloud_infrastructure_cost + self.markup_cost + self.cost_model_cpu_cost,
                        },
                        "filter": [{"field": "data_source", "operation": "exact", "parameter": "Pod"}],
                        "conditionals": {
                            OCPUsageLineItemDailySummary: {
                                "exclude": [
                                    {
                                        "field": "namespace",
                                        "operation": "exact",
                                        "parameter": "Workers Unallocated Capacity",
                                    },
                                    {
                                        "field": "namespace",
                                        "operation": "exact",
                                        "parameter": "Platform Unallocated Capacity",
                                    },
                                ],
                            },
                        },
                        "cost_units_key": "raw_currency",
                        "usage_units_key": "Core-Hours",
                        "sum_columns": ["usage", "request", "limit", "sup_total", "cost_total", "infra_total"],
                    },
                    "memory": {
                        "aggregates": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": self.cost_model_memory_supplementary_cost,
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": self.cost_model_memory_supplementary_cost,
                            "infra_raw": self.cloud_infrastructure_cost,
                            "infra_usage": self.cost_model_memory_infrastructure_cost,
                            "infra_markup": self.markup_cost,
                            "infra_total": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_memory_infrastructure_cost,
                            "cost_raw": self.cloud_infrastructure_cost,
                            "cost_usage": self.cost_model_memory_cost,
                            "cost_markup": self.markup_cost,
                            "cost_total": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_memory_cost,
                            "usage": Sum("pod_usage_memory_gigabyte_hours"),
                            "request": Sum("pod_request_memory_gigabyte_hours"),
                            "limit": Sum("pod_limit_memory_gigabyte_hours"),
                        },
                        "capacity_aggregate": {"capacity": Max("cluster_capacity_memory_gigabyte_hours")},
                        "default_ordering": {"usage": "desc"},
                        "annotations": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": self.cost_model_memory_supplementary_cost,
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": self.cost_model_memory_supplementary_cost,
                            "infra_raw": self.cloud_infrastructure_cost,
                            "infra_usage": self.cost_model_memory_infrastructure_cost,
                            "infra_markup": self.markup_cost,
                            "infra_total": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_memory_infrastructure_cost,
                            "cost_raw": self.cloud_infrastructure_cost,
                            "cost_usage": self.cost_model_memory_cost,
                            "cost_markup": self.markup_cost,
                            "cost_total": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_memory_cost,
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
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
                            "cost_total": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_memory_cost,
                        },
                        "filter": [{"field": "data_source", "operation": "exact", "parameter": "Pod"}],
                        "conditionals": {
                            OCPUsageLineItemDailySummary: {
                                "exclude": [
                                    {
                                        "field": "namespace",
                                        "operation": "exact",
                                        "parameter": "Workers Unallocated Capacity",
                                    },
                                    {
                                        "field": "namespace",
                                        "operation": "exact",
                                        "parameter": "Platform Unallocated Capacity",
                                    },
                                ],
                            },
                        },
                        "cost_units_key": "raw_currency",
                        "usage_units_key": "GB-Hours",
                        "sum_columns": ["usage", "request", "limit", "cost_total", "sup_total", "infra_total"],
                    },
                    "volume": {
                        "tag_column": "volume_labels",
                        "aggregates": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": self.cost_model_volume_supplementary_cost,
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": self.cost_model_volume_supplementary_cost,
                            "infra_raw": self.cloud_infrastructure_cost,
                            "infra_usage": self.cost_model_volume_infrastructure_cost,
                            "infra_markup": self.markup_cost,
                            "infra_total": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_volume_infrastructure_cost,
                            "cost_raw": self.cloud_infrastructure_cost,
                            "cost_usage": self.cost_model_volume_cost,
                            "cost_markup": self.markup_cost,
                            "cost_total": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_volume_cost,
                            "usage": Sum("persistentvolumeclaim_usage_gigabyte_months"),
                            "request": Sum("volume_request_storage_gigabyte_months"),
                            "capacity": Sum("persistentvolumeclaim_capacity_gigabyte_months"),
                        },
                        "default_ordering": {"usage": "desc"},
                        "annotations": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": self.cost_model_volume_supplementary_cost,
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": self.cost_model_volume_supplementary_cost,
                            "infra_raw": self.cloud_infrastructure_cost,
                            "infra_usage": self.cost_model_volume_infrastructure_cost,
                            "infra_markup": self.markup_cost,
                            "infra_total": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_volume_infrastructure_cost,
                            "cost_raw": self.cloud_infrastructure_cost,
                            "cost_usage": self.cost_model_volume_cost,
                            "cost_markup": self.markup_cost,
                            "cost_total": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_volume_cost,
                            "usage": Sum("persistentvolumeclaim_usage_gigabyte_months"),
                            "request": Sum("volume_request_storage_gigabyte_months"),
                            "capacity": Sum("persistentvolumeclaim_capacity_gigabyte_months"),
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
                            "usage_units": Value("GB-Mo", output_field=CharField()),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "delta_key": {
                            "usage": Sum("persistentvolumeclaim_usage_gigabyte_months"),
                            "request": Sum("volume_request_storage_gigabyte_months"),
                            "cost_total": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_volume_cost,
                        },
                        "filter": [{"field": "data_source", "operation": "exact", "parameter": "Storage"}],
                        "cost_units_key": "raw_currency",
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

    @cached_property
    def cost_model_supplementary_cost(self):
        """Return supplementary cost model costs."""
        return self.__cost_model_cost(cost_model_rate_type="Supplementary")

    @cached_property
    def cost_model_infrastructure_cost(self):
        """Return infrastructure cost model costs."""
        return self.__cost_model_cost(cost_model_rate_type="Infrastructure")

    @cached_property
    def cost_model_cost(self):
        """Return all cost model costs."""
        return self.__cost_model_cost()

    @cached_property
    def cost_model_cpu_supplementary_cost(self):
        """Return supplementary cost model costs."""
        return self.__cost_model_cpu_cost(cost_model_rate_type="Supplementary")

    @cached_property
    def cost_model_cpu_infrastructure_cost(self):
        """Return infrastructure cost model costs."""
        return self.__cost_model_cpu_cost(cost_model_rate_type="Infrastructure")

    @cached_property
    def cost_model_cpu_cost(self):
        """Return all cost model costs."""
        return self.__cost_model_cpu_cost()

    @cached_property
    def cost_model_memory_supplementary_cost(self):
        """Return supplementary cost model costs."""
        return self.__cost_model_memory_cost(cost_model_rate_type="Supplementary")

    @cached_property
    def cost_model_memory_infrastructure_cost(self):
        """Return infrastructure cost model costs."""
        return self.__cost_model_memory_cost(cost_model_rate_type="Infrastructure")

    @cached_property
    def cost_model_memory_cost(self):
        """Return all cost model costs."""
        return self.__cost_model_memory_cost()

    @cached_property
    def cost_model_volume_supplementary_cost(self):
        """Return supplementary cost model costs."""
        return self.__cost_model_volume_cost(cost_model_rate_type="Supplementary")

    @cached_property
    def cost_model_volume_infrastructure_cost(self):
        """Return infrastructure cost model costs."""
        return self.__cost_model_volume_cost(cost_model_rate_type="Infrastructure")

    @cached_property
    def cost_model_volume_cost(self):
        """Return all cost model costs."""
        return self.__cost_model_volume_cost()

    @cached_property
    def cloud_infrastructure_cost(self):
        """Return ORM term for cloud infra costs."""
        return Sum(
            Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
            * Coalesce("infra_exchange_rate", Value(1, output_field=DecimalField()))
        )

    @cached_property
    def cloud_infrastructure_cost_by_project(self):
        """Return ORM term for cloud infra costs by project."""
        return Sum(
            Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
            * Coalesce("infra_exchange_rate", Value(1, output_field=DecimalField()))
        )

    @cached_property
    def markup_cost(self):
        """Return ORM term for cloud infra markup."""
        return Sum(
            Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
            * Coalesce("infra_exchange_rate", Value(1, output_field=DecimalField()))
        )

    @cached_property
    def markup_cost_by_project(self):
        """Return ORM term for cloud infra markup by project."""
        return Sum(
            Coalesce(F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField()))
            * Coalesce("infra_exchange_rate", Value(1, output_field=DecimalField()))
        )
