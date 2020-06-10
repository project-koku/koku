#
# Copyright 2019 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Provider Mapper for OCP on Azure Reports."""
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import CharField
from django.db.models import Count
from django.db.models import DecimalField
from django.db.models import F
from django.db.models import Max
from django.db.models import Sum
from django.db.models import Value
from django.db.models.functions import Coalesce

from api.models import Provider
from api.report.provider_map import ProviderMap
from reporting.models import OCPAzureComputeSummary
from reporting.models import OCPAzureCostLineItemDailySummary
from reporting.models import OCPAzureCostLineItemProjectDailySummary
from reporting.models import OCPAzureCostSummary
from reporting.models import OCPAzureCostSummaryByAccount
from reporting.models import OCPAzureCostSummaryByLocation
from reporting.models import OCPAzureCostSummaryByService
from reporting.models import OCPAzureDatabaseSummary
from reporting.models import OCPAzureNetworkSummary
from reporting.models import OCPAzureStorageSummary


class OCPAzureProviderMap(ProviderMap):
    """OCP on Azure Provider Map."""

    def __init__(self, provider, report_type):
        """Constructor."""
        self._mapping = [
            {
                "provider": Provider.OCP_AZURE,
                "alias": "subscription_guid",
                "annotations": {"cluster": "cluster_id"},
                "end_date": "costentrybill__billing_period_end",
                "filters": {
                    "project": {"field": "namespace", "operation": "icontains"},
                    "cluster": [
                        {"field": "cluster_alias", "operation": "icontains", "composition_key": "cluster_filter"},
                        {"field": "cluster_id", "operation": "icontains", "composition_key": "cluster_filter"},
                    ],
                    "node": {"field": "node", "operation": "icontains"},
                    "subscription_guid": [
                        {"field": "subscription_guid", "operation": "icontains", "composition_key": "account_filter"}
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
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(F("pretax_cost")),
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
                            "cost_raw": Sum(F("pretax_cost")),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                        },
                        "annotations": {
                            # Cost is the first column in annotations so that it
                            # can reference the original database column 'markup_cost'
                            # If cost comes after the markup_cost annotaton, then
                            # Django will reference the annotated value, which is
                            # a Sum() and things will break trying to add
                            # a column with the sum of another column.
                            "cost_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "infra_raw": Sum(F("pretax_cost")),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "cost_raw": Sum(F("pretax_cost")),
                            "cost_usage": Value(0, output_field=DecimalField()),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
                        },
                        "count": None,
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
                    "costs_by_project": {
                        "tables": {
                            "query": OCPAzureCostLineItemProjectDailySummary,
                            "total": OCPAzureCostLineItemProjectDailySummary,
                        },
                        "tag_column": "pod_labels",
                        "aggregates": {
                            "infra_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("pod_cost"),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("pod_cost"),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                        },
                        "annotations": {
                            "infra_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("pod_cost"),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("pod_cost"),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
                        },
                        "count": None,
                        "delta_key": {
                            "cost_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
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
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(F("pretax_cost")),
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
                            "cost_raw": Sum(F("pretax_cost")),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "usage": Sum(F("usage_quantity")),
                            "usage_units": Coalesce(Max("unit_of_measure"), Value("Storage Type Placeholder")),
                        },
                        "annotations": {
                            "infra_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(F("pretax_cost")),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(F("pretax_cost")),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "usage": Sum(F("usage_quantity")),
                            # FIXME: Waiting on MSFT for usage_units default
                            "usage_units": Coalesce(Max("unit_of_measure"), Value("Storage Type Placeholder")),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
                        },
                        "count": None,
                        "delta_key": {"usage": Sum("usage_quantity")},
                        "filter": [{"field": "service_name", "operation": "icontains", "parameter": "Storage"}],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit_of_measure",
                        "usage_units_fallback": "Storage Type Placeholder",  # FIXME
                        "sum_columns": ["usage", "cost_total", "sup_total", "infra_total"],
                        "default_ordering": {"usage": "desc"},
                    },
                    "storage_by_project": {
                        "tables": {
                            "query": OCPAzureCostLineItemProjectDailySummary,
                            "total": OCPAzureCostLineItemProjectDailySummary,
                        },
                        "tag_column": "pod_labels",
                        "aggregates": {
                            "infra_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("pod_cost"),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("pod_cost"),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "usage": Sum("usage_quantity"),
                            # FIXME: Waiting on MSFT for usage_units default
                            "usage_units": Coalesce(Max("unit_of_measure"), Value("Storage Type Placeholder")),
                        },
                        "annotations": {
                            "infra_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("pod_cost"),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("pod_cost"),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "usage": Sum("usage_quantity"),
                            "usage_units": Coalesce(Max("unit_of_measure"), Value("Storage Type Placeholder")),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
                        },
                        "count": None,
                        "delta_key": {"usage": Sum("usage_quantity")},
                        "filter": [{"field": "service_name", "operation": "icontains", "parameter": "Storage"}],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit_of_measure",
                        "usage_units_fallback": "Storage Type Placeholder",  # FIXME
                        "sum_columns": ["usage", "cost_total", "sup_total", "infra_total"],
                        "default_ordering": {"usage": "desc"},
                    },
                    "instance_type": {
                        "aggregates": {
                            "infra_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(F("pretax_cost")),
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
                            "cost_raw": Sum(F("pretax_cost")),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "count": Count("resource_id", distinct=True),
                            "usage": Sum(F("usage_quantity")),
                            # FIXME: Waiting on MSFT for usage_units default
                            "usage_units": Coalesce(Max("unit_of_measure"), Value("Instance Type Placeholder")),
                        },
                        "aggregate_key": "usage_quantity",
                        "annotations": {
                            "infra_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(F("pretax_cost")),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                Coalesce(F("pretax_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(F("pretax_cost")),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "count": Count("resource_id", distinct=True),
                            "count_units": Value("instances", output_field=CharField()),
                            "usage": Sum(F("usage_quantity")),
                            # FIXME: Waiting on MSFT for usage_units default
                            "usage_units": Coalesce(Max("unit_of_measure"), Value("Instance Type Placeholder")),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
                        },
                        "count": "resource_id",
                        "delta_key": {"usage": Sum("usage_quantity")},
                        "filter": [{"field": "instance_type", "operation": "isnull", "parameter": False}],
                        "group_by": ["instance_type"],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit_of_measure",
                        "usage_units_fallback": "Instance Type Placeholder",  # FIXME
                        "count_units_fallback": "instances",
                        "sum_columns": ["usage", "cost_total", "sup_total", "infra_total", "count"],
                        "default_ordering": {"usage": "desc"},
                    },
                    "instance_type_by_project": {
                        "tables": {
                            "query": OCPAzureCostLineItemProjectDailySummary,
                            "total": OCPAzureCostLineItemProjectDailySummary,
                        },
                        "tag_column": "pod_labels",
                        "aggregates": {
                            "infra_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("pod_cost"),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("pod_cost"),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "count": Count("resource_id", distinct=True),
                            "usage": Sum("usage_quantity"),
                            # FIXME: Waiting on MSFT for usage_units default
                            "usage_units": Coalesce(Max("unit_of_measure"), Value("Instance Type Placeholder")),
                        },
                        "aggregate_key": "usage_quantity",
                        "annotations": {
                            "infra_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum("pod_cost"),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                Coalesce(F("pod_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum("pod_cost"),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(
                                Coalesce(F("project_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_units": Coalesce(Max("currency"), Value("USD")),
                            "count": Count("resource_id", distinct=True),
                            "count_units": Value("instances", output_field=CharField()),
                            "usage": Sum("usage_quantity"),
                            # FIXME: Waiting on MSFT for usage_units default
                            "usage_units": Coalesce(Max("unit_of_measure"), Value("Instance Type Placeholder")),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
                        },
                        "count": "resource_id",
                        "delta_key": {"usage": Sum("usage_quantity")},
                        "filter": [{"field": "instance_type", "operation": "isnull", "parameter": False}],
                        "group_by": ["instance_type"],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit_of_measure",
                        "usage_units_fallback": "Instance Type Placeholder",  # FIXME
                        "count_units_fallback": "instances",
                        "sum_columns": ["usage", "cost_total", "sup_total", "infra_total", "count"],
                        "default_ordering": {"usage": "desc"},
                    },
                    "tags": {"default_ordering": {"cost_total": "desc"}},
                },
                "start_date": "usage_start",
                "tables": {"query": OCPAzureCostLineItemDailySummary, "total": OCPAzureCostLineItemDailySummary},
            }
        ]

        self.views = {
            "costs": {
                "default": OCPAzureCostSummary,
                "subscription_guid": OCPAzureCostSummaryByAccount,
                "service_name": OCPAzureCostSummaryByService,
                "resource_location": OCPAzureCostSummaryByLocation,
            },
            "instance_type": {"default": OCPAzureComputeSummary, "instance_type": OCPAzureComputeSummary},
            "storage": {"default": OCPAzureStorageSummary},
            "database": {"default": OCPAzureDatabaseSummary, "service_name": OCPAzureDatabaseSummary},
            "network": {"default": OCPAzureNetworkSummary, "service_name": OCPAzureNetworkSummary},
        }
        super().__init__(provider, report_type)
