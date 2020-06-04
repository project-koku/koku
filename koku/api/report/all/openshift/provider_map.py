#
# Copyright 2018 Red Hat, Inc.
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
"""Provider Mapper for OCP on All Reports."""
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
from reporting.models import OCPAllComputeSummary
from reporting.models import OCPAllCostLineItemDailySummary
from reporting.models import OCPAllCostLineItemProjectDailySummary
from reporting.models import OCPAllCostSummary
from reporting.models import OCPAllCostSummaryByAccount
from reporting.models import OCPAllCostSummaryByRegion
from reporting.models import OCPAllCostSummaryByService
from reporting.models import OCPAllDatabaseSummary
from reporting.models import OCPAllNetworkSummary
from reporting.models import OCPAllStorageSummary


class OCPAllProviderMap(ProviderMap):
    """OCP on All Infrastructure Provider Map."""

    def __init__(self, provider, report_type):
        """Constructor."""
        self._mapping = [
            {
                "provider": Provider.OCP_ALL,
                "alias": "account_alias__account_alias",
                "annotations": {
                    "cluster": "cluster_id",
                    "project": "namespace",
                    "account": "usage_account_id",
                    "service": "product_code",
                    "az": "availability_zone",
                },
                "end_date": "usage_end",
                "filters": {
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
                    "source_type": {"field": "source_type", "operation": "icontains"},
                },
                "group_by_options": ["account", "service", "region", "cluster", "project", "node", "product_family"],
                "tag_column": "tags",
                "report_type": {
                    "costs": {
                        "aggregates": {
                            "infra_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(F("unblended_cost")),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(F("unblended_cost")),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                        },
                        "annotations": {
                            "infra_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(F("unblended_cost")),
                            "infra_usage": Value(0, output_field=DecimalField()),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(F("unblended_cost")),
                            "cost_usage": Value(0, output_field=DecimalField()),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency_code"), Value("USD")),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
                        },
                        "count": None,
                        "delta_key": {
                            "cost_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            )
                        },
                        "filter": [{}],
                        "cost_units_key": "currency_code",
                        "cost_units_fallback": "USD",
                        "sum_columns": [
                            "cost_total",
                            "sup_total",
                            "infra_total",
                            "infra_raw",
                            "infra_usage",
                            "infra_markup",
                        ],
                        "default_ordering": {"cost_total": "desc"},
                    },
                    "costs_by_project": {
                        "tables": {
                            "query": OCPAllCostLineItemProjectDailySummary,
                            "total": OCPAllCostLineItemProjectDailySummary,
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
                            "cost_units": Coalesce(Max("currency_code"), Value("USD")),
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
                        "cost_units_key": "currency_code",
                        "cost_units_fallback": "USD",
                        "sum_columns": [
                            "infra_raw",
                            "infra_markup",
                            "infra_usage",
                            "cost_total",
                            "sup_total",
                            "infra_total",
                        ],
                        "default_ordering": {"cost_total": "desc"},
                    },
                    "storage": {
                        "aggregates": {
                            "infra_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(F("unblended_cost")),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(F("unblended_cost")),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency_code"), Value("USD")),
                            "usage": Sum(F("usage_amount")),
                            "usage_units": Coalesce(Max("unit"), Value("GB-Mo")),
                        },
                        "annotations": {
                            "infra_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(F("unblended_cost")),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(F("unblended_cost")),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency_code"), Value("USD")),
                            "usage": Sum(F("usage_amount")),
                            "usage_units": Coalesce(Max("unit"), Value("GB-Mo")),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
                        },
                        "count": None,
                        "delta_key": {"usage": Sum("usage_amount")},
                        "filter": [{}],
                        "or_filter": [
                            {"field": "product_family", "operation": "icontains", "parameter": "Storage"},
                            {"field": "product_code", "operation": "icontains", "parameter": "Storage"},
                        ],
                        "cost_units_key": "currency_code",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit",
                        "usage_units_fallback": "GB-Mo",
                        "sum_columns": [
                            "usage",
                            "infra_raw",
                            "infra_markup",
                            "infra_usage",
                            "cost_total",
                            "sup_total",
                            "infra_total",
                        ],
                        "default_ordering": {"usage": "desc"},
                    },
                    "storage_by_project": {
                        "tables": {
                            "query": OCPAllCostLineItemProjectDailySummary,
                            "total": OCPAllCostLineItemProjectDailySummary,
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
                            "cost_units": Coalesce(Max("currency_code"), Value("USD")),
                            "usage": Sum("usage_amount"),
                            "usage_units": Coalesce(Max("unit"), Value("GB-Mo")),
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
                            "cost_units": Coalesce(Max("currency_code"), Value("USD")),
                            "usage": Sum("usage_amount"),
                            "usage_units": Coalesce(Max("unit"), Value("GB-Mo")),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
                        },
                        "count": None,
                        "delta_key": {"usage": Sum("usage_amount")},
                        "filter": [{}],
                        "or_filter": [
                            {"field": "product_family", "operation": "icontains", "parameter": "Storage"},
                            {"field": "product_code", "operation": "icontains", "parameter": "Storage"},
                        ],
                        "cost_units_key": "currency_code",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit",
                        "usage_units_fallback": "GB-Mo",
                        "sum_columns": [
                            "usage",
                            "cost_total",
                            "sup_total",
                            "infra_total",
                            "infra_raw",
                            "infra_usage",
                            "infra_markup",
                        ],
                        "default_ordering": {"usage": "desc"},
                    },
                    "instance_type": {
                        "aggregates": {
                            "infra_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(F("unblended_cost")),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(Value(0, output_field=DecimalField())),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(Value(0, output_field=DecimalField())),
                            "cost_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(F("unblended_cost")),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency_code"), Value("USD")),
                            "count": Count("resource_id", distinct=True),
                            "usage": Sum(F("usage_amount")),
                            "usage_units": Coalesce(Max("unit"), Value("GB-Mo")),
                        },
                        "aggregate_key": "usage_amount",
                        "annotations": {
                            "infra_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(F("unblended_cost")),
                            "infra_usage": Sum(Value(0, output_field=DecimalField())),
                            "infra_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Value(0, output_field=DecimalField()),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Value(0, output_field=DecimalField()),
                            "cost_total": Sum(
                                Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(F("unblended_cost")),
                            "cost_usage": Sum(Value(0, output_field=DecimalField())),
                            "cost_markup": Sum(Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))),
                            "cost_units": Coalesce(Max("currency_code"), Value("USD")),
                            "count": Count("resource_id", distinct=True),
                            "count_units": Value("instances", output_field=CharField()),
                            "usage": Sum(F("usage_amount")),
                            "usage_units": Coalesce(Max("unit"), Value("Hrs")),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
                        },
                        "count": "resource_id",
                        "delta_key": {"usage": Sum("usage_amount")},
                        "filter": [{"field": "instance_type", "operation": "isnull", "parameter": False}],
                        "group_by": ["instance_type"],
                        "cost_units_key": "currency_code",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit",
                        "usage_units_fallback": "Hrs",
                        "count_units_fallback": "instances",
                        "sum_columns": [
                            "usage",
                            "cost_total",
                            "sup_total",
                            "infra_total",
                            "infra_raw",
                            "infra_markup",
                            "infra_usage",
                            "count",
                        ],
                        "default_ordering": {"usage": "desc"},
                    },
                    "instance_type_by_project": {
                        "tables": {
                            "query": OCPAllCostLineItemProjectDailySummary,
                            "total": OCPAllCostLineItemProjectDailySummary,
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
                            "cost_units": Coalesce(Max("currency_code"), Value("USD")),
                            "count": Count("resource_id", distinct=True),
                            "usage": Sum("usage_amount"),
                            "usage_units": Coalesce(Max("unit"), Value("GB-Mo")),
                        },
                        "aggregate_key": "usage_amount",
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
                            "cost_units": Coalesce(Max("currency_code"), Value("USD")),
                            "count": Count("resource_id", distinct=True),
                            "count_units": Value("instances", output_field=CharField()),
                            "usage": Sum("usage_amount"),
                            "usage_units": Coalesce(Max("unit"), Value("Hrs")),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
                        },
                        "count": "resource_id",
                        "delta_key": {"usage": Sum("usage_amount")},
                        "filter": [{"field": "instance_type", "operation": "isnull", "parameter": False}],
                        "group_by": ["instance_type"],
                        "cost_units_key": "currency_code",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit",
                        "usage_units_fallback": "Hrs",
                        "count_units_fallback": "instances",
                        "sum_columns": [
                            "usage",
                            "cost_total",
                            "sup_total",
                            "infra_total",
                            "infra_raw",
                            "infra_markup",
                            "infra_usage",
                            "count",
                        ],
                        "default_ordering": {"usage": "desc"},
                    },
                    "tags": {"default_ordering": {"cost_total": "desc"}},
                },
                "start_date": "usage_start",
                "tables": {"query": OCPAllCostLineItemDailySummary, "total": OCPAllCostLineItemDailySummary},
            }
        ]

        self.views = {
            "costs": {
                "default": OCPAllCostSummary,
                "account": OCPAllCostSummaryByAccount,
                "region": OCPAllCostSummaryByRegion,
                "service": OCPAllCostSummaryByService,
                "product_family": OCPAllCostSummaryByService,
            },
            "instance_type": {"default": OCPAllComputeSummary, "instance_type": OCPAllComputeSummary},
            "storage": {"default": OCPAllStorageSummary, "product_family": OCPAllStorageSummary},
            "database": {"default": OCPAllDatabaseSummary, "service": OCPAllDatabaseSummary},
            "network": {"default": OCPAllNetworkSummary, "service": OCPAllNetworkSummary},
        }
        super().__init__(provider, report_type)
