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
from masu.processor import is_feature_cost_3083_all_labels_enabled
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

    @cached_property
    def check_unleash_for_tag_column_cost_3038(self):
        if is_feature_cost_3083_all_labels_enabled(self._schema_name):
            return "all_labels"
        return "pod_labels"

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

    def __cost_model_distributed_cost(self, cost_model_rate_type=None):
        """Return ORM term for cost model distributed cost."""

        if cost_model_rate_type:
            return Sum(
                Case(
                    When(
                        cost_model_rate_type=cost_model_rate_type,
                        then=Coalesce(F("distributed_cost"), Value(0, output_field=DecimalField())),
                    ),
                    default=Value(0, output_field=DecimalField()),
                )
                * Coalesce("exchange_rate", Value(1, output_field=DecimalField())),
            )
        else:
            return Sum(
                (Coalesce(F("distributed_cost"), Value(0, output_field=DecimalField())))
                * Coalesce("exchange_rate", Value(1, output_field=DecimalField())),
            )

    def __init__(self, provider, report_type, schema_name):
        """Constructor."""
        self._schema_name = schema_name
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
                    "persistentvolumeclaim": {"field": "persistentvolumeclaim", "operation": "icontains"},
                    "storageclass": {"field": "storageclass", "operation": "icontains"},
                    "pod": {"field": "pod", "operation": "icontains"},
                    "node": {"field": "node", "operation": "icontains"},
                    "infrastructures": {
                        "field": "cluster_id",
                        "operation": "exact",
                        "custom": ProviderAccessor(Provider.PROVIDER_OCP).infrastructure_key_list,
                    },
                },
                "group_by_options": ["cluster", "project", "node", "persistentvolumeclaim"],
                "tag_column": "pod_labels",  # default for if a report type does not have a tag_column
                "report_type": {
                    "costs": {
                        "tag_column": self.check_unleash_for_tag_column_cost_3038,
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
                        "tag_column": self.check_unleash_for_tag_column_cost_3038,
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
                            "cost_total_distributed": self.cloud_infrastructure_cost_by_project
                            + self.markup_cost_by_project
                            + self.cost_model_cost
                            + self.cost_model_distributed_cost_by_project,
                            "cost_platform_distributed": self.platform_distributed_cost_by_project,
                            "cost_worker_unallocated_distributed": self.worker_unallocated_distributed_cost_by_project,
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
                            "cost_total_distributed": self.cloud_infrastructure_cost_by_project
                            + self.markup_cost_by_project
                            + self.cost_model_cost
                            + self.cost_model_distributed_cost_by_project,
                            "cost_platform_distributed": self.platform_distributed_cost_by_project,
                            "cost_worker_unallocated_distributed": self.worker_unallocated_distributed_cost_by_project,
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
                            "cost_total_distributed": self.cloud_infrastructure_cost_by_project
                            + self.markup_cost_by_project
                            + self.cost_model_cost
                            + self.cost_model_distributed_cost_by_project,
                        },
                        "filter": [{}],
                        "cost_units_key": "raw_currency",
                        "sum_columns": ["cost_total", "infra_total", "sup_total"],
                    },
                    "cpu": {
                        "tag_column": "pod_labels",
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
                        "capacity_aggregate": {
                            "cluster": {
                                "capacity": Max("cluster_capacity_cpu_core_hours"),
                                "cluster": Coalesce("cluster_alias", "cluster_id"),
                            },
                            "cluster_instance_counts": {
                                "capacity_count": Max("node_capacity_cpu_cores"),
                                "cluster": Coalesce("cluster_alias", "cluster_id"),
                            },
                            "node": {
                                "capacity": Max("node_capacity_cpu_core_hours"),
                                "capacity_count": Max("node_capacity_cpu_cores"),
                            },
                        },
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
                            "capacity": Max("cluster_capacity_cpu_core_hours"),  # overwritten in capacity aggregation
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "delta_key": {
                            "usage": Sum("pod_usage_cpu_core_hours"),
                            "request": Sum("pod_request_cpu_core_hours"),
                            "cost_total": self.cloud_infrastructure_cost + self.markup_cost + self.cost_model_cpu_cost,
                            "cost_total_distributed": self.cloud_infrastructure_cost_by_project
                            + self.markup_cost_by_project
                            + self.cost_model_cost
                            + self.cost_model_distributed_cost_by_project,
                        },
                        "filter": [{"field": "data_source", "operation": "exact", "parameter": "Pod"}],
                        "conditionals": {
                            OCPUsageLineItemDailySummary: {
                                "exclude": [
                                    {
                                        "field": "namespace",
                                        "operation": "exact",
                                        "parameter": "Worker unallocated",
                                    },
                                    {
                                        "field": "namespace",
                                        "operation": "exact",
                                        "parameter": "Platform unallocated",
                                    },
                                ],
                            },
                        },
                        "cost_units_key": "raw_currency",
                        "usage_units_key": "Core-Hours",
                        "count_units_key": "Core",
                        "sum_columns": ["usage", "request", "limit", "sup_total", "cost_total", "infra_total"],
                    },
                    "memory": {
                        "tag_column": "pod_labels",
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
                        "capacity_aggregate": {
                            "cluster": {
                                "capacity": Max("cluster_capacity_memory_gigabyte_hours"),
                                "cluster": Coalesce("cluster_alias", "cluster_id"),
                            },
                            "cluster_instance_counts": {
                                "capacity_count": Max("node_capacity_memory_gigabytes"),
                                "cluster": Coalesce("cluster_alias", "cluster_id"),
                            },
                            "node": {
                                "capacity": Max("node_capacity_memory_gigabyte_hours"),
                                "capacity_count": Max("node_capacity_memory_gigabytes"),
                            },
                        },
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
                            "capacity": Max(
                                "cluster_capacity_memory_gigabyte_hours"
                            ),  # This is to keep the order, overwritten with capacity aggregate
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
                                        "parameter": "Worker unallocated",
                                    },
                                    {
                                        "field": "namespace",
                                        "operation": "exact",
                                        "parameter": "Platform unallocated",
                                    },
                                ],
                            },
                        },
                        "cost_units_key": "raw_currency",
                        "usage_units_key": "GB-Hours",
                        "count_units_key": "GB",
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
                            "usage": Sum(
                                Coalesce(
                                    F("persistentvolumeclaim_usage_gigabyte_months"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "request": Sum(
                                Coalesce(
                                    F("volume_request_storage_gigabyte_months"), Value(0, output_field=DecimalField())
                                )
                            ),
                            "capacity": Sum(
                                Coalesce(
                                    F("persistentvolumeclaim_capacity_gigabyte_months"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "persistent_volume_claim": ArrayAgg(
                                "persistentvolumeclaim", filter=Q(persistentvolumeclaim__isnull=False), distinct=True
                            ),
                            "storage_class": ArrayAgg(
                                "storageclass", filter=Q(storageclass__isnull=False), distinct=True
                            ),
                        },
                        "default_ordering": {"usage": "desc"},
                        "capacity_aggregate": {
                            "cluster_instance_counts": {
                                "capacity_count": Sum(
                                    Coalesce(
                                        F("persistentvolumeclaim_capacity_gigabyte"),
                                        Value(0, output_field=DecimalField()),
                                    )
                                ),
                                "cluster": Coalesce("cluster_alias", "cluster_id"),
                            },
                            "node": {
                                "capacity": Sum(
                                    Coalesce(
                                        F("persistentvolumeclaim_capacity_gigabyte_months"),
                                        Value(0, output_field=DecimalField()),
                                    )
                                ),
                                "capacity_count": Sum(
                                    Coalesce(
                                        F("persistentvolumeclaim_capacity_gigabyte"),
                                        Value(0, output_field=DecimalField()),
                                    )
                                ),
                            },
                        },
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
                            "usage": Sum(
                                Coalesce(
                                    F("persistentvolumeclaim_usage_gigabyte_months"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "request": Sum(
                                Coalesce(
                                    F("volume_request_storage_gigabyte_months"), Value(0, output_field=DecimalField())
                                )
                            ),
                            "capacity": Sum(
                                Coalesce(
                                    F("persistentvolumeclaim_capacity_gigabyte_months"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
                            "usage_units": Value("GB-Mo", output_field=CharField()),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                            "persistent_volume_claim": ArrayAgg(
                                "persistentvolumeclaim", filter=Q(persistentvolumeclaim__isnull=False), distinct=True
                            ),
                            "storage_class": ArrayAgg(
                                "storageclass", filter=Q(storageclass__isnull=False), distinct=True
                            ),
                        },
                        "delta_key": {
                            "usage": Sum(
                                Coalesce(
                                    F("persistentvolumeclaim_usage_gigabyte_months"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "request": Sum(
                                Coalesce(
                                    F("volume_request_storage_gigabyte_months"), Value(0, output_field=DecimalField())
                                )
                            ),
                            "cost_total": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_volume_cost,
                        },
                        "filter": [{"field": "data_source", "operation": "exact", "parameter": "Storage"}],
                        "cost_units_key": "raw_currency",
                        "usage_units_key": "GB-Mo",
                        "count_units_key": "GB",
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
                ("persistentvolumeclaim",): OCPVolumeSummaryP,
                ("cluster", "persistentvolumeclaim"): OCPVolumeSummaryP,
                ("persistentvolumeclaim", "project"): OCPVolumeSummaryByProjectP,
                ("cluster", "persistentvolumeclaim", "project"): OCPVolumeSummaryByProjectP,
            },
        }
        super().__init__(provider, report_type, schema_name)

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

    @cached_property
    def platform_distributed_cost_by_project(self):
        """Return platform distributed cost model costs."""
        return self.__cost_model_distributed_cost(cost_model_rate_type="platform_distributed")

    @cached_property
    def worker_unallocated_distributed_cost_by_project(self):
        """Return worker unallocated distributed cost model costs."""
        return self.__cost_model_distributed_cost(cost_model_rate_type="worker_distributed")

    @cached_property
    def cost_model_distributed_cost_by_project(self):
        """Return cost model distributed cost."""
        return self.__cost_model_distributed_cost()
