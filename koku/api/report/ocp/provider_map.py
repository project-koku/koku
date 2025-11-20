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
from django.db.models import IntegerField
from django.db.models import Max
from django.db.models import Q
from django.db.models import Sum
from django.db.models import Value
from django.db.models import When
from django.db.models.functions import Coalesce
from django.db.models.functions import JSONObject

from api.models import Provider
from api.report.provider_map import ProviderMap
from providers.provider_access import ProviderAccessor
from reporting.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPCostSummaryByNodeP
from reporting.provider.ocp.models import OCPCostSummaryByProjectP
from reporting.provider.ocp.models import OCPCostSummaryP
from reporting.provider.ocp.models import OCPGpuSummaryByNodeP
from reporting.provider.ocp.models import OCPGpuSummaryByProjectP
from reporting.provider.ocp.models import OCPGpuSummaryP
from reporting.provider.ocp.models import OCPNetworkSummaryByNodeP
from reporting.provider.ocp.models import OCPNetworkSummaryByProjectP
from reporting.provider.ocp.models import OCPNetworkSummaryP
from reporting.provider.ocp.models import OCPPodSummaryByNodeP
from reporting.provider.ocp.models import OCPPodSummaryByProjectP
from reporting.provider.ocp.models import OCPPodSummaryP
from reporting.provider.ocp.models import OCPVirtualMachineSummaryP
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
                        + Coalesce(F("cost_model_volume_cost"), Value(0, output_field=DecimalField()))
                        + Coalesce(F("cost_model_gpu_cost"), Value(0, output_field=DecimalField())),
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
                    + Coalesce(F("cost_model_gpu_cost"), Value(0, output_field=DecimalField()))
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

    def __cost_model_gpu_cost(self, cost_model_rate_type=None):
        """Return ORM term for GPU cost model cost"""
        if cost_model_rate_type:
            return Sum(
                Case(
                    When(
                        cost_model_rate_type=cost_model_rate_type,
                        then=Coalesce(F("gpu_cost"), Value(0, output_field=DecimalField())),
                    ),
                    default=Value(0, output_field=DecimalField()),
                )
            )
        else:
            return Sum(Coalesce(F("gpu_cost"), Value(0, output_field=DecimalField())))

    def __cost_model_distributed_cost(self, cost_model_rate_type, exchange_rate_column):
        return Sum(
            Case(
                When(
                    cost_model_rate_type=cost_model_rate_type,
                    then=Coalesce(F("distributed_cost"), Value(0, output_field=DecimalField())),
                ),
                default=Value(0, output_field=DecimalField()),
            )
            * Coalesce(exchange_rate_column, Value(1, output_field=DecimalField())),
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
                    "vm_name": {"field": "vm_name", "operation": "icontains"},
                    "vendor": {"field": "gpu_vendor_name", "operation": "icontains"},
                    "model": {"field": "gpu_model_name", "operation": "icontains"},
                    "infrastructures": {
                        "field": "cluster_id",
                        "operation": "exact",
                        "custom": ProviderAccessor(Provider.PROVIDER_OCP).infrastructure_key_list,
                    },
                },
                "group_by_options": ["cluster", "project", "node", "persistentvolumeclaim", "storageclass"],
                "tag_column": "pod_labels",  # default for if a report type does not have a tag_column
                "report_type": {
                    "costs": {
                        "tag_column": "all_labels",
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
                        "tag_column": "all_labels",
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
                            "cost_total_distributed": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_cost
                            + self.distributed_platform_cost
                            + self.distributed_worker_cost
                            + self.distributed_unattributed_network_cost
                            + self.distributed_unattributed_storage_cost,
                            "cost_platform_distributed": self.distributed_platform_cost,
                            "cost_worker_unallocated_distributed": self.distributed_worker_cost,
                            "cost_network_unattributed_distributed": self.distributed_unattributed_network_cost,
                            "cost_storage_unattributed_distributed": self.distributed_unattributed_storage_cost,
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
                            "cost_total_distributed": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_cost
                            + self.distributed_platform_cost
                            + self.distributed_worker_cost
                            + self.distributed_unattributed_storage_cost
                            + self.distributed_unattributed_network_cost,
                            "cost_platform_distributed": self.distributed_platform_cost,
                            "cost_worker_unallocated_distributed": self.distributed_worker_cost,
                            "cost_network_unattributed_distributed": self.distributed_unattributed_network_cost,
                            "cost_storage_unattributed_distributed": self.distributed_unattributed_storage_cost,
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                            "cost_group": F("cost_category__name"),
                        },
                        "capacity_aggregate": {},
                        "delta_key": {
                            "cost_total": self.cloud_infrastructure_cost + self.markup_cost + self.cost_model_cost,
                            "cost_total_distributed": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_cost
                            + self.distributed_platform_cost
                            + self.distributed_worker_cost
                            + self.distributed_unattributed_storage_cost
                            + self.distributed_unattributed_network_cost,
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
                            "cost_total_distributed": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_cpu_cost
                            + self.distributed_platform_cost
                            + self.distributed_worker_cost
                            + self.distributed_unattributed_storage_cost
                            + self.distributed_unattributed_network_cost,
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
                            "cost_total_distributed": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_cpu_cost
                            + self.distributed_platform_cost
                            + self.distributed_worker_cost
                            + self.distributed_unattributed_storage_cost
                            + self.distributed_unattributed_network_cost,
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
                            "cost_total_distributed": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_cpu_cost
                            + self.distributed_platform_cost
                            + self.distributed_worker_cost
                            + self.distributed_unattributed_storage_cost
                            + self.distributed_unattributed_network_cost,
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
                                    {
                                        "field": "namespace",
                                        "operation": "exact",
                                        "parameter": "Network unattributed",
                                    },
                                ],
                            },
                        },
                        "cost_units_key": "raw_currency",
                        "usage_units_key": "Core-Hours",
                        "count_units_key": "Core",
                        "capacity_count_key": "node_capacity_cpu_cores",
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
                            "cost_total_distributed": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_memory_cost
                            + self.distributed_platform_cost
                            + self.distributed_worker_cost
                            + self.distributed_unattributed_storage_cost
                            + self.distributed_unattributed_network_cost,
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
                            "cost_total_distributed": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_memory_cost
                            + self.distributed_platform_cost
                            + self.distributed_worker_cost
                            + self.distributed_unattributed_storage_cost
                            + self.distributed_unattributed_network_cost,
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
                            "usage": Sum("pod_usage_memory_gigabyte_hours"),
                            "request": Sum("pod_request_memory_gigabyte_hours"),
                            "limit": Sum("pod_limit_memory_gigabyte_hours"),
                            "capacity": Max(
                                "cluster_capacity_memory_gigabyte_hours"
                            ),  # This is to keep the order, overwritten with capacity aggregate
                            "usage_units": Value("GiB-Hours", output_field=CharField()),
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
                            "cost_total_distributed": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_memory_cost
                            + self.distributed_platform_cost
                            + self.distributed_worker_cost
                            + self.distributed_unattributed_storage_cost
                            + self.distributed_unattributed_network_cost,
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
                                    {
                                        "field": "namespace",
                                        "operation": "exact",
                                        "parameter": "Network unattributed",
                                    },
                                ],
                            },
                        },
                        "cost_units_key": "raw_currency",
                        "usage_units_key": "GiB-Hours",
                        "count_units_key": "GiB",
                        "capacity_count_key": "node_capacity_memory_gigabytes",
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
                                "capacity_count": Max(
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
                                "capacity_count": Max(
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
                            "usage_units": Value("GiB-Mo", output_field=CharField()),
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
                        "usage_units_key": "GiB-Mo",
                        "count_units_key": "GiB",
                        "capacity_count_key": "persistentvolumeclaim_capacity_gigabyte",
                        "sum_columns": ["usage", "request", "cost_total", "sup_total", "infra_total"],
                    },
                    "network": {
                        "tag_column": "all_labels",
                        "aggregates": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": self.cost_model_supplementary_cost,
                            "infra_raw": self.cloud_infrastructure_cost,
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": self.markup_cost,
                            "infra_total": self.cloud_infrastructure_cost + self.markup_cost,
                            "cost_raw": self.cloud_infrastructure_cost,
                            "cost_usage": self.cost_model_cost,
                            "cost_markup": self.markup_cost,
                            "cost_total": self.cloud_infrastructure_cost + self.markup_cost,
                            "usage": Sum(
                                Coalesce(
                                    F("infrastructure_data_in_gigabytes"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    F("infrastructure_data_out_gigabytes"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "data_transfer_in": Sum(
                                Coalesce(
                                    F("infrastructure_data_in_gigabytes"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "data_transfer_out": Sum(
                                Coalesce(
                                    F("infrastructure_data_out_gigabytes"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                        },
                        "default_ordering": {"usage": "desc"},
                        "capacity_aggregate": {},
                        "annotations": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": self.cost_model_supplementary_cost,
                            "infra_raw": self.cloud_infrastructure_cost,
                            "infra_usage": self.cost_model_infrastructure_cost,
                            "infra_markup": self.markup_cost,
                            "infra_total": self.cloud_infrastructure_cost + self.markup_cost,
                            "cost_raw": self.cloud_infrastructure_cost,
                            "cost_usage": self.cost_model_cost,
                            "cost_markup": self.markup_cost,
                            "cost_total": self.cloud_infrastructure_cost + self.markup_cost + self.cost_model_cost,
                            "usage": Sum(
                                Coalesce(
                                    F("infrastructure_data_in_gigabytes"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    F("infrastructure_data_out_gigabytes"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "data_transfer_in": Sum(
                                Coalesce(
                                    F("infrastructure_data_in_gigabytes"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "data_transfer_out": Sum(
                                Coalesce(
                                    F("infrastructure_data_out_gigabytes"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            # the `currency_annotation` is inserted by the `annotations` property of the query-handler
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
                            "usage_units": Value("GB", output_field=CharField()),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                        },
                        "delta_key": {
                            "usage": Sum(
                                Coalesce(
                                    F("infrastructure_data_in_gigabytes"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    F("infrastructure_data_out_gigabytes"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "data_transfer_in": Sum(
                                Coalesce(
                                    F("infrastructure_data_in_gigabytes"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "data_transfer_out": Sum(
                                Coalesce(
                                    F("infrastructure_data_out_gigabytes"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_total": self.cloud_infrastructure_cost + self.markup_cost,
                        },
                        "filter": [],
                        "conditionals": {
                            OCPUsageLineItemDailySummary: {
                                "include": [
                                    {
                                        "field": "namespace",
                                        "operation": "exact",
                                        "parameter": "Network unattributed",
                                    },
                                ],
                            },
                        },
                        "cost_units_key": "raw_currency",
                        "usage_units_key": "GB",
                        "sum_columns": [
                            "usage",
                            "data_transfer_in",
                            "data_transfer_out",
                            "cost_total",
                            "sup_total",
                            "infra_total",
                        ],
                    },
                    "gpu": {
                        "tables": {"query": OCPGpuSummaryP},
                        "group_by_options": ["cluster", "project", "node", "vendor", "model"],
                        "tag_column": "pod_labels",
                        "aggregates": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": self.__cost_model_gpu_cost(cost_model_rate_type="Supplementary"),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": self.__cost_model_gpu_cost(cost_model_rate_type="Supplementary"),
                            "infra_raw": Sum(Value(0, output_field=DecimalField())),
                            "infra_usage": self.__cost_model_gpu_cost(cost_model_rate_type="Infrastructure"),
                            "infra_markup": Sum(Value(0, output_field=DecimalField())),
                            "infra_total": self.__cost_model_gpu_cost(cost_model_rate_type="Infrastructure"),
                            "cost_raw": Sum(Value(0, output_field=DecimalField())),
                            "cost_usage": self.__cost_model_gpu_cost(),
                            "cost_markup": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": self.__cost_model_gpu_cost(),
                        },
                        "default_ordering": {"cost_total": "desc"},
                        "capacity_aggregate": {},
                        "annotations": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": self.__cost_model_gpu_cost(cost_model_rate_type="Supplementary"),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": self.__cost_model_gpu_cost(cost_model_rate_type="Supplementary"),
                            "infra_raw": Sum(Value(0, output_field=DecimalField())),
                            "infra_usage": self.__cost_model_gpu_cost(cost_model_rate_type="Infrastructure"),
                            "infra_markup": Sum(Value(0, output_field=DecimalField())),
                            "infra_total": self.__cost_model_gpu_cost(cost_model_rate_type="Infrastructure"),
                            "cost_raw": Sum(Value(0, output_field=DecimalField())),
                            "cost_usage": self.__cost_model_gpu_cost(),
                            "cost_markup": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": self.__cost_model_gpu_cost(),
                            "cost_units": Coalesce("currency_annotation", Value("USD", output_field=CharField())),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                            "vendor": F("gpu_vendor_name"),
                            "model": F("gpu_model_name"),
                            "memory": Max(
                                Coalesce(F("gpu_memory_capacity_mib"), Value(0, output_field=DecimalField()))
                            ),
                            "memory_units": Value("MiB", output_field=CharField()),
                            "gpu_hours": Sum(Coalesce(F("gpu_hours"), Value(0, output_field=DecimalField()))),
                            "gpu_count": Sum(Coalesce(F("gpu_count"), Value(0, output_field=IntegerField()))),
                        },
                        "delta_key": {},
                        "filter": [],
                        "cost_units_key": "raw_currency",
                        "sum_columns": [
                            "cost_total",
                            "sup_total",
                            "infra_total",
                        ],
                    },
                    "virtual_machines": {
                        "tag_column": "pod_labels",
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
                            "request_cpu": Coalesce(
                                Sum("pod_request_cpu_core_hours") / 24, Sum(Value(0, output_field=DecimalField()))
                            ),
                            "request_memory": Coalesce(
                                Sum("pod_request_memory_gigabyte_hours") / 24,
                                Sum(Value(0, output_field=DecimalField())),
                            ),
                            "request_cpu_units": Max(Value("Core", output_field=CharField())),
                            "request_memory_units": Max(Value("GiB", output_field=CharField())),
                            "cost_total_distributed": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_cost
                            + self.distributed_platform_cost
                            + self.distributed_worker_cost
                            + self.distributed_unattributed_network_cost
                            + self.distributed_unattributed_storage_cost,
                            "cost_platform_distributed": self.distributed_platform_cost,
                            "cost_worker_unallocated_distributed": self.distributed_worker_cost,
                            "cost_network_unattributed_distributed": self.distributed_unattributed_network_cost,
                            "cost_storage_unattributed_distributed": self.distributed_unattributed_storage_cost,
                        },
                        "capacity_aggregate": {},
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
                            "cost_units": Max(Coalesce("currency_annotation", Value("USD", output_field=CharField()))),
                            "request_cpu": Coalesce(
                                Sum("pod_request_cpu_core_hours") / 24, Sum(Value(0, output_field=DecimalField()))
                            ),
                            "request_memory": Coalesce(
                                Sum("pod_request_memory_gigabyte_hours") / 24,
                                Sum(Value(0, output_field=DecimalField())),
                            ),
                            "request_cpu_units": Value("Core", output_field=CharField()),
                            "request_memory_units": Value("GiB", output_field=CharField()),
                            "cost_total_distributed": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_cost
                            + self.distributed_platform_cost
                            + self.distributed_worker_cost
                            + self.distributed_unattributed_network_cost
                            + self.distributed_unattributed_storage_cost,
                            "cost_platform_distributed": self.distributed_platform_cost,
                            "cost_worker_unallocated_distributed": self.distributed_worker_cost,
                            "cost_network_unattributed_distributed": self.distributed_unattributed_network_cost,
                            "cost_storage_unattributed_distributed": self.distributed_unattributed_storage_cost,
                            "cluster": Max(Coalesce("cluster_alias", "cluster_id")),
                            "node": Max(F("node")),
                            "project": Max("namespace"),
                            "source_uuid": ArrayAgg(
                                F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True
                            ),
                            "storage": ArrayAgg(
                                JSONObject(
                                    pvc_name=F("persistentvolumeclaim"),
                                    storage_class=F("storageclass"),
                                    usage=F("persistentvolumeclaim_usage_gigabyte_months"),
                                    capacity=F("persistentvolumeclaim_capacity_gigabyte_months"),
                                    usage_units=Value("GiB-Mo", output_field=CharField()),
                                ),
                                distinct=True,
                                filter=~Q(persistentvolumeclaim_usage_gigabyte_months__isnull=True),
                            ),
                            "tags": ArrayAgg(F("pod_labels"), distinct=True),
                        },
                        "delta_key": {
                            "request": Sum("pod_request_cpu_core_hours"),
                            "cost_total": self.cloud_infrastructure_cost + self.markup_cost + self.cost_model_cost,
                            "cost_total_distributed": self.cloud_infrastructure_cost
                            + self.markup_cost
                            + self.cost_model_cost
                            + self.distributed_platform_cost
                            + self.distributed_worker_cost
                            + self.distributed_unattributed_storage_cost
                            + self.distributed_unattributed_network_cost,
                        },
                        "filter": [],
                        "default_ordering": {"cost_total": "desc"},
                        "tables": {"query": OCPVirtualMachineSummaryP},
                        "group_by": ["vm_name"],
                        "cost_units_key": "raw_currency",
                        "usage_units_key": "Core-Hours",
                        "count_units_key": "Core",
                        "storage_usage_units_key": "GiB-Mo",
                        "sum_columns": ["usage", "request", "limit", "sup_total", "cost_total", "infra_total"],
                        "vm_name": Max("vm_name"),
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
                ("node",): OCPPodSummaryByNodeP,
                ("project",): OCPPodSummaryByProjectP,
                ("cluster", "project"): OCPPodSummaryByProjectP,
                ("cluster", "node"): OCPPodSummaryByNodeP,
            },
            "memory": {
                "default": OCPPodSummaryP,
                ("cluster",): OCPPodSummaryP,
                ("node",): OCPPodSummaryByNodeP,
                ("project",): OCPPodSummaryByProjectP,
                ("cluster", "project"): OCPPodSummaryByProjectP,
                ("cluster", "node"): OCPPodSummaryByNodeP,
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
            "network": {
                "default": OCPNetworkSummaryP,
                ("cluster",): OCPNetworkSummaryP,
                ("node",): OCPNetworkSummaryByNodeP,
                ("project",): OCPNetworkSummaryByProjectP,
                ("cluster", "project"): OCPNetworkSummaryByProjectP,
            },
            "virtual_machines": {
                "default": OCPVirtualMachineSummaryP,
            },
            "gpu": {
                "default": OCPGpuSummaryP,
                ("cluster",): OCPGpuSummaryP,
                ("node",): OCPGpuSummaryByNodeP,
                ("project",): OCPGpuSummaryByProjectP,
                ("cluster", "node"): OCPGpuSummaryByNodeP,
                ("cluster", "project"): OCPGpuSummaryByProjectP,
                ("vendor",): OCPGpuSummaryP,
                ("model",): OCPGpuSummaryP,
                ("cluster", "vendor"): OCPGpuSummaryP,
                ("cluster", "model"): OCPGpuSummaryP,
                ("node", "vendor"): OCPGpuSummaryByNodeP,
                ("node", "model"): OCPGpuSummaryByNodeP,
                ("project", "vendor"): OCPGpuSummaryByProjectP,
                ("project", "model"): OCPGpuSummaryByProjectP,
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
    def cost_model_gpu_supplementary_cost(self):
        """Return supplementary GPU cost model costs."""
        return self.__cost_model_gpu_cost(cost_model_rate_type="Supplementary")

    @cached_property
    def cost_model_gpu_infrastructure_cost(self):
        """Return infrastructure GPU cost model costs."""
        return self.__cost_model_gpu_cost(cost_model_rate_type="Infrastructure")

    @cached_property
    def cost_model_gpu_cost(self):
        """Return all GPU cost model costs."""
        return self.__cost_model_gpu_cost()

    @cached_property
    def cloud_infrastructure_cost(self):
        """Return ORM term for cloud infra costs."""
        return Sum(
            Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
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
    def distributed_unattributed_storage_cost(self):
        """The unattributed storage cost needs to have the infra exchange rate applied to it."""
        return self.__cost_model_distributed_cost("unattributed_storage", "infra_exchange_rate")

    @cached_property
    def distributed_unattributed_network_cost(self):
        """The unattributed network cost needs to have the infra exchange rate applied to it."""
        return self.__cost_model_distributed_cost("unattributed_network", "infra_exchange_rate")

    @cached_property
    def distributed_platform_cost(self):
        """Platform distributed cost"""
        return self.__cost_model_distributed_cost("platform_distributed", "exchange_rate")

    @cached_property
    def distributed_worker_cost(self):
        """Worker unallocated distributed cost"""
        return self.__cost_model_distributed_cost("worker_distributed", "exchange_rate")
