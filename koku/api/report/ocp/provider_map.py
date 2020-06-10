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
"""Provider Mapper for OCP Reports."""
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import CharField
from django.db.models import DecimalField
from django.db.models import F
from django.db.models import Max
from django.db.models import Sum
from django.db.models import Value
from django.db.models.functions import Coalesce

from api.models import Provider
from api.report.provider_map import ProviderMap
from koku.database import KeyDecimalTransform
from providers.provider_access import ProviderAccessor
from reporting.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPCostSummary
from reporting.provider.ocp.models import OCPCostSummaryByNode
from reporting.provider.ocp.models import OCPCostSummaryByProject
from reporting.provider.ocp.models import OCPPodSummary
from reporting.provider.ocp.models import OCPPodSummaryByProject
from reporting.provider.ocp.models import OCPVolumeSummary
from reporting.provider.ocp.models import OCPVolumeSummaryByProject


class OCPProviderMap(ProviderMap):
    """OCP Provider Map."""

    def __init__(self, provider, report_type):
        """Constructor."""
        self._mapping = [
            {
                "provider": Provider.PROVIDER_OCP,
                "annotations": {"cluster": "cluster_id"},
                "end_date": "usage_end",
                "filters": {
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
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("supplementary_monthly_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("supplementary_monthly_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_monthly_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("supplementary_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_monthly_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("supplementary_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                        },
                        "default_ordering": {"cost_total": "desc"},
                        "annotations": {
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("supplementary_monthly_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("supplementary_monthly_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_monthly_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            # Cost =  Supplementary[field] + Infrastructure[filed]
                            # Note: if a value was currently zero it was left out, unless both sup & infra are zero
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("supplementary_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_monthly_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("supplementary_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_units": Value("USD", output_field=CharField()),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
                        },
                        "capacity_aggregate": {},
                        "delta_key": {
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("supplementary_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            )
                        },
                        "filter": [{}],
                        "cost_units_key": "USD",
                        "sum_columns": ["cost_total", "infra_total", "sup_total"],
                    },
                    "costs_by_project": {
                        "tables": {"query": OCPUsageLineItemDailySummary},
                        "aggregates": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("supplementary_monthly_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("supplementary_monthly_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_monthly_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_markup": Sum(
                                Coalesce(
                                    F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField())
                                )
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField())
                                )
                            ),
                            # Cost =  Supplementary[field] + Infrastructure[filed]
                            # Note: if a value was currently zero it was left out, unless both sup & infra are zero
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("supplementary_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_monthly_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_markup": Sum(
                                Coalesce(
                                    F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField())
                                )
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("supplementary_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField())
                                )
                            ),
                        },
                        "default_ordering": {"cost_total": "desc"},
                        "annotations": {
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("supplementary_monthly_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("supplementary_monthly_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_monthly_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_markup": Sum(
                                Coalesce(
                                    F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField())
                                )
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField())
                                )
                            ),
                            # Cost =  Supplementary[field] + Infrastructure[filed]
                            # Note: if a value was currently zero it was left out, unless both sup & infra are zero
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("supplementary_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_monthly_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_markup": Sum(
                                Coalesce(
                                    F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField())
                                )
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("supplementary_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField())
                                )
                            ),
                            "cost_units": Value("USD", output_field=CharField()),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "cost": Value(0, output_field=DecimalField()),
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
                        },
                        "capacity_aggregate": {},
                        "delta_key": {
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("supplementary_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_monthly_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    F("infrastructure_project_markup_cost"), Value(0, output_field=DecimalField())
                                )
                            )
                        },
                        "filter": [{}],
                        "cost_units_key": "USD",
                        "sum_columns": ["cost_total", "infra_total", "sup_total"],
                    },
                    "cpu": {
                        "aggregates": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "usage": Sum("pod_usage_cpu_core_hours"),
                            "request": Sum("pod_request_cpu_core_hours"),
                            "limit": Sum("pod_limit_cpu_core_hours"),
                        },
                        "capacity_aggregate": {"capacity": Max("cluster_capacity_cpu_core_hours")},
                        "default_ordering": {"usage": "desc"},
                        "annotations": {
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_units": Value("USD", output_field=CharField()),
                            "usage_units": Value("Core-Hours", output_field=CharField()),
                            "usage": Sum("pod_usage_cpu_core_hours"),
                            "request": Sum("pod_request_cpu_core_hours"),
                            "limit": Sum("pod_limit_cpu_core_hours"),
                            "capacity": {
                                "total": Max("total_capacity_cpu_core_hours"),
                                "cluster": Max("cluster_capacity_cpu_core_hours"),
                            },
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
                        },
                        "delta_key": {
                            "usage": Sum("pod_usage_cpu_core_hours"),
                            "request": Sum("pod_request_cpu_core_hours"),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("cpu", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("cpu", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                        },
                        "filter": [{"field": "data_source", "operation": "exact", "parameter": "Pod"}],
                        "cost_units_key": "USD",
                        "usage_units_key": "Core-Hours",
                        "sum_columns": ["usage", "request", "limit", "sup_total", "cost_total", "infra_total"],
                    },
                    "memory": {
                        "aggregates": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "usage": Sum("pod_usage_memory_gigabyte_hours"),
                            "request": Sum("pod_request_memory_gigabyte_hours"),
                            "limit": Sum("pod_limit_memory_gigabyte_hours"),
                        },
                        "capacity_aggregate": {"capacity": Max("cluster_capacity_memory_gigabyte_hours")},
                        "default_ordering": {"usage": "desc"},
                        "annotations": {
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_units": Value("USD", output_field=CharField()),
                            "usage": Sum("pod_usage_memory_gigabyte_hours"),
                            "request": Sum("pod_request_memory_gigabyte_hours"),
                            "limit": Sum("pod_limit_memory_gigabyte_hours"),
                            "capacity": {
                                "total": Max("total_capacity_memory_gigabyte_hours"),
                                "cluster": Max("cluster_capacity_memory_gigabyte_hours"),
                            },
                            "usage_units": Value("GB-Hours", output_field=CharField()),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
                        },
                        "delta_key": {
                            "usage": Sum("pod_usage_memory_gigabyte_hours"),
                            "request": Sum("pod_request_memory_gigabyte_hours"),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("memory", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("memory", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                        },
                        "filter": [{"field": "data_source", "operation": "exact", "parameter": "Pod"}],
                        "cost_units_key": "USD",
                        "usage_units_key": "GB-Hours",
                        "sum_columns": ["usage", "request", "limit", "cost_total", "sup_total", "infra_total"],
                    },
                    "volume": {
                        "tag_column": "volume_labels",
                        "aggregates": {
                            "sup_raw": Sum(Value(0, output_field=DecimalField())),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_markup": Sum(Value(0, output_field=DecimalField())),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "usage": Sum("persistentvolumeclaim_usage_gigabyte_months"),
                            "request": Sum("volume_request_storage_gigabyte_months"),
                        },
                        "capacity_aggregate": {"capacity": Sum("persistentvolumeclaim_capacity_gigabyte_months")},
                        "default_ordering": {"usage": "desc"},
                        "annotations": {
                            "sup_raw": Value(0, output_field=DecimalField()),
                            "sup_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "sup_markup": Value(0, output_field=DecimalField()),
                            "sup_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "infra_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "infra_total": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_raw": Sum(
                                Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_usage": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                            ),
                            "cost_markup": Sum(
                                Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                            "usage": Sum("persistentvolumeclaim_usage_gigabyte_months"),
                            "request": Sum("volume_request_storage_gigabyte_months"),
                            "capacity": {
                                "total": Sum("persistentvolumeclaim_capacity_gigabyte_months"),
                                "cluster": Sum("persistentvolumeclaim_capacity_gigabyte_months"),
                            },
                            "cost_units": Value("USD", output_field=CharField()),
                            "usage_units": Value("GB-Mo", output_field=CharField()),
                            "clusters": ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True),
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
                        },
                        "delta_key": {
                            "usage": Sum("persistentvolumeclaim_usage_gigabyte_months"),
                            "request": Sum("volume_request_storage_gigabyte_months"),
                            "cost_total": Sum(
                                Coalesce(
                                    KeyDecimalTransform("storage", "supplementary_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))
                                + Coalesce(
                                    KeyDecimalTransform("storage", "infrastructure_usage_cost"),
                                    Value(0, output_field=DecimalField()),
                                )
                                + Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=DecimalField()))
                            ),
                        },
                        "filter": [{"field": "data_source", "operation": "exact", "parameter": "Storage"}],
                        "cost_units_key": "USD",
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
            "costs": {"default": OCPCostSummary, "cluster": OCPCostSummary, "node": OCPCostSummaryByNode},
            "costs_by_project": {"default": OCPCostSummaryByProject, "project": OCPCostSummaryByProject},
            "cpu": {
                "default": OCPPodSummary,
                "project": OCPPodSummaryByProject,
                "cpu": OCPPodSummary,
                "cluster": OCPPodSummary,
            },
            "memory": {
                "default": OCPPodSummary,
                "project": OCPPodSummaryByProject,
                "memory": OCPPodSummary,
                "cluster": OCPPodSummary,
            },
            "volume": {"default": OCPVolumeSummary, "project": OCPVolumeSummaryByProject, "cluster": OCPVolumeSummary},
        }
        super().__init__(provider, report_type)
