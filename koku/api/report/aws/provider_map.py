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
"""Provider Mapper for AWS Reports."""

from django.db.models import CharField, DecimalField, F, Max, Sum, Value
from django.db.models.expressions import ExpressionWrapper
from django.db.models.functions import Coalesce

from api.report.provider_map import ProviderMap
from reporting.models import AWSCostEntryLineItemDailySummary


class AWSProviderMap(ProviderMap):
    """AWS Provider Map."""

    def __init__(self, provider, report_type):
        """Constructor."""
        self._mapping = [
            {
                'provider': 'AWS',
                'alias': 'account_alias__account_alias',
                'annotations': {
                    'account': 'usage_account_id',
                    'service': 'product_code',
                    'az': 'availability_zone'
                },
                'end_date': 'usage_end',
                'filters': {
                    'account': [
                        {
                            'field': 'account_alias__account_alias',
                            'operation': 'icontains',
                            'composition_key': 'account_filter'
                        },
                        {
                            'field': 'usage_account_id',
                            'operation': 'icontains',
                            'composition_key': 'account_filter'
                        }
                    ],
                    'service': {
                        'field': 'product_code',
                        'operation': 'icontains'
                    },
                    'az': {
                        'field': 'availability_zone',
                        'operation': 'icontains'
                    },
                    'region': {
                        'field': 'region',
                        'operation': 'icontains'
                    },
                    'product_family': {
                        'field': 'product_family',
                        'operation': 'icontains'
                    }
                },
                'group_by_options': ['service', 'account', 'region', 'az', 'product_family'],
                'tag_column': 'tags',
                'report_type': {
                    'costs': {
                        'aggregates': {
                            'cost': Sum(
                                Coalesce(F('unblended_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum('unblended_cost'),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'markup_cost': Sum(
                                Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                        },
                        'aggregate_key': 'unblended_cost',
                        'annotations': {
                            'cost': Sum(
                                Coalesce(F('unblended_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum('unblended_cost'),
                            'derived_cost': Value(0, output_field=DecimalField()),
                            'markup_cost': Sum(
                                Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD'))
                        },
                        'delta_key': {'cost': Sum(ExpressionWrapper(F('unblended_cost') + F('markup_cost'),
                                                                    output_field=DecimalField()))},
                        'filter': [{}],
                        'cost_units_key': 'currency_code',
                        'cost_units_fallback': 'USD',
                        'sum_columns': ['cost', 'infrastructure_cost', 'derived_cost', 'markup_cost'],
                        'default_ordering': {'cost': 'desc'},
                    },
                    'instance_type': {
                        'aggregates': {
                            'cost': Sum(
                                Coalesce(F('unblended_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum('unblended_cost'),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'markup_cost': Sum('markup_cost'),
                            'count': Sum(Value(0, output_field=DecimalField())),
                            'usage': Sum('usage_amount'),
                        },
                        'aggregate_key': 'usage_amount',
                        'annotations': {
                            'cost': Sum(
                                Coalesce(F('unblended_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum('unblended_cost'),
                            'derived_cost': Value(0, output_field=DecimalField()),
                            'markup_cost': Sum(
                                Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD')),
                            # The summary table already already has counts
                            'count': Max('resource_count'),
                            'count_units': Value('instances', output_field=CharField()),
                            'usage': Sum('usage_amount'),
                            'usage_units': Coalesce(Max('unit'), Value('Hrs'))
                        },
                        'delta_key': {'usage': Sum('usage_amount')},
                        'filter': [{
                            'field': 'instance_type',
                            'operation': 'isnull',
                            'parameter': False
                        }, ],
                        'group_by': ['instance_type'],
                        'cost_units_key': 'currency_code',
                        'cost_units_fallback': 'USD',
                        'usage_units_key': 'unit',
                        'usage_units_fallback': 'Hrs',
                        'count_units_fallback': 'instances',
                        'sum_columns': ['usage', 'cost', 'infrastructure_cost',
                                        'derived_cost', 'markup_cost', 'count'],
                        'default_ordering': {'usage': 'desc'},
                    },
                    'storage': {
                        'aggregates': {
                            'cost': Sum(
                                Coalesce(F('unblended_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum('unblended_cost'),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'markup_cost': Sum('markup_cost'),
                            'usage': Sum('usage_amount'),
                        },
                        'aggregate_key': 'usage_amount',
                        'annotations': {
                            'cost': Sum(
                                Coalesce(F('unblended_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum('unblended_cost'),
                            'derived_cost': Value(0, output_field=DecimalField()),
                            'markup_cost': Sum(
                                Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD')),
                            'usage': Sum('usage_amount'),
                            'usage_units': Coalesce(Max('unit'), Value('GB-Mo'))
                        },
                        'delta_key': {'usage': Sum('usage_amount')},
                        'filter': [{
                            'field': 'product_family',
                            'operation': 'contains',
                            'parameter': 'Storage'
                        }, {
                            'field': 'unit',
                            'operation': 'exact',
                            'parameter': 'GB-Mo'
                        }],
                        'cost_units_key': 'currency_code',
                        'cost_units_fallback': 'USD',
                        'usage_units_key': 'unit',
                        'usage_units_fallback': 'GB-Mo',
                        'sum_columns': ['usage', 'cost', 'infrastructure_cost',
                                        'derived_cost', 'markup_cost'],
                        'default_ordering': {'usage': 'desc'},
                    },
                    'tags': {
                        'default_ordering': {'cost': 'desc'},
                    },
                },
                'start_date': 'usage_start',
                'tables': {
                    'query': AWSCostEntryLineItemDailySummary,
                },
            },
        ]
        super().__init__(provider, report_type)
