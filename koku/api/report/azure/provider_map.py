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
"""Provider Mapper for Azure Reports."""
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
from reporting.models import AzureComputeSummary
from reporting.models import AzureCostEntryLineItemDailySummary
from reporting.models import AzureCostSummary
from reporting.models import AzureCostSummaryByAccount
from reporting.models import AzureCostSummaryByLocation
from reporting.models import AzureCostSummaryByService
from reporting.models import AzureDatabaseSummary
from reporting.models import AzureNetworkSummary
from reporting.models import AzureStorageSummary


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
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
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
                            # FIXME: Waiting on MSFT for usage_units default
                            "usage_units": Coalesce(Max("unit_of_measure"), Value("Instance Type Placeholder")),
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
                        },
                        "delta_key": {"usage": Sum("usage_quantity")},
                        "filter": [{"field": "instance_type", "operation": "isnull", "parameter": False}],
                        "group_by": ["instance_type"],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit_of_measure",
                        "usage_units_fallback": "Instance Type Placeholder",  # FIXME: Waiting on MSFT
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
                            "usage_units": Coalesce(Max("unit_of_measure"), Value("Storage Type Placeholder")),
                            "source_uuid": ArrayAgg(F("source_uuid"), distinct=True),
                        },
                        "delta_key": {"usage": Sum("usage_quantity")},
                        "filter": [{"field": "service_name", "operation": "icontains", "parameter": "Storage"}],
                        "cost_units_key": "currency",
                        "cost_units_fallback": "USD",
                        "usage_units_key": "unit_of_measure",
                        "usage_units_fallback": "Storage Type Placeholder",  # FIXME
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
                "default": AzureCostSummary,
                "subscription_guid": AzureCostSummaryByAccount,
                "resource_location": AzureCostSummaryByLocation,
                "service_name": AzureCostSummaryByService,
            },
            "instance_type": {"default": AzureComputeSummary, "instance_type": AzureComputeSummary},
            "storage": {"default": AzureStorageSummary},
            "database": {"default": AzureDatabaseSummary, "service_name": AzureDatabaseSummary},
            "network": {"default": AzureNetworkSummary, "service_name": AzureNetworkSummary},
        }
        super().__init__(provider, report_type)
