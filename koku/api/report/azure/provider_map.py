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

from django.db.models import CharField, DecimalField, F, Max, Sum, Value
from django.db.models.functions import Coalesce

from api.report.provider_map import ProviderMap
from reporting.models import AzureCostEntryLineItemDailySummary


class AzureProviderMap(ProviderMap):
    """Azure Provider Map."""

    def __init__(self, provider, report_type):
        """Constructor."""
        self._mapping = [
            {
                'provider': 'AZURE',
                'alias': 'subscription_guid',  # FIXME: probably wrong
                'annotations': {},
                'end_date': 'costentrybill__billing_period_end',
                'filters': {
                    'subscription_guid': [
                        {
                            'field': 'subscription_guid',
                            'operation': 'icontains',
                            'composition_key': 'account_filter'
                        },
                    ],
                    'service_name': {
                        'field': 'service_name',
                        'operation': 'icontains'
                    },
                    'resource_location': {
                        'field': 'resource_location',
                        'operation': 'icontains'
                    },
                    'instance_type': {
                        'field': 'instance_type',
                        'operation': 'icontains'
                    }
                },
                'group_by_options': ['service_name', 'subscription_guid',
                                     'resource_location', 'instance_type'],
                'tag_column': 'tags',
                'report_type': {
                    'costs': {
                        'aggregates': {
                            'cost': Sum(
                                Coalesce(F('pretax_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum('pretax_cost'),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'markup_cost': Sum(
                                Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                        },
                        'aggregate_key': 'pretax_cost',
                        'annotations': {
                            'cost': Sum(
                                Coalesce(F('pretax_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum('pretax_cost'),
                            'derived_cost': Value(0, output_field=DecimalField()),
                            'markup_cost': Sum(
                                Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'cost_units': Coalesce(Max('currency'), Value('USD'))
                        },
                        'delta_key': {
                            'cost': Sum(
                                Coalesce(F('pretax_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            )
                        },
                        'filter': [{}],
                        'cost_units_key': 'currency',
                        'cost_units_fallback': 'USD',
                        'sum_columns': ['cost', 'infrastructure_cost', 'derived_cost', 'markup_cost'],
                        'default_ordering': {'cost': 'desc'},
                    },
                    'instance_type': {
                        'aggregates': {
                            'cost': Sum(
                                Coalesce(F('pretax_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum('pretax_cost'),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'markup_cost': Sum(
                                Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'count': Sum(Value(0, output_field=DecimalField())),
                            'usage': Sum('usage_quantity'),
                        },
                        'aggregate_key': 'usage_quantity',
                        'annotations': {
                            'cost': Sum(
                                Coalesce(F('pretax_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum('pretax_cost'),
                            'derived_cost': Value(0, output_field=DecimalField()),
                            'markup_cost': Sum(
                                Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'cost_units': Coalesce(Max('currency'), Value('USD')),
                            'count': Max('instance_count'),
                            'count_units': Value('instance_types', output_field=CharField()),
                            'usage': Sum('usage_quantity'),
                            # Waiting on MSFT for usage_units default
                            'usage_units': Coalesce(Max('unit_of_measure'), Value('Instance Type Placeholder'))
                        },
                        'delta_key': {'usage': Sum('usage_quantity')},
                        'filter': [{
                            'field': 'instance_type',
                            'operation': 'isnull',
                            'parameter': False
                        }],
                        'group_by': ['instance_type'],
                        'cost_units_key': 'currency',
                        'cost_units_fallback': 'USD',
                        'usage_units_key': 'unit_of_measure',
                        'usage_units_fallback': 'Instance Type Placeholder',  # Waiting on MSFT
                        'count_units_fallback': 'instances',
                        'sum_columns': ['usage', 'cost', 'infrastructure_cost',
                                        'derived_cost', 'markup_cost', 'count'],
                        'default_ordering': {'usage': 'desc'},
                    },
                    'storage': {
                        'aggregates': {
                            'cost': Sum(
                                Coalesce(F('pretax_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'usage': Sum('usage_quantity'),
                            'infrastructure_cost': Sum('pretax_cost'),
                            'markup_cost': Sum(
                                Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'count': Sum(Value(0, output_field=DecimalField())),
                        },
                        'aggregate_key': 'usage_quantity',
                        'annotations': {
                            'cost': Sum(
                                Coalesce(F('pretax_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum('pretax_cost'),
                            'derived_cost': Value(0, output_field=DecimalField()),
                            'markup_cost': Sum(
                                Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'cost_units': Coalesce(Max('currency'), Value('USD')),
                            'count': Max('instance_count'),
                            'count_units': Value('instances', output_field=CharField()),
                            'usage': Sum('usage_quantity'),
                            # Waiting on MSFT for usage_units default
                            'usage_units': Coalesce(Max('unit_of_measure'), Value('Storage Type Placeholder'))
                        },
                        'delta_key': {'usage': Sum('usage_quantity')},
                        'filter': [{
                            'field': 'service_name',
                            'operation': 'contains',
                            'parameter': 'Storage'
                        }],
                        'cost_units_key': 'currency',
                        'cost_units_fallback': 'USD',
                        'usage_units_key': 'unit_of_measure',
                        'usage_units_fallback': 'Storage Type Placeholder',
                        'sum_columns': ['usage', 'cost', 'infrastructure_cost', 'derived_cost', 'markup_cost'],
                        'default_ordering': {'usage': 'desc'},
                    },
                    'tags': {
                        'default_ordering': {'cost': 'desc'},
                    },
                },
                'start_date': 'costentrybill__billing_period_start',
                'tables': {
                    'query': AzureCostEntryLineItemDailySummary,
                },
            },
        ]
        super().__init__(provider, report_type)
