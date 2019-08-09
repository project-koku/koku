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
"""Provider Mapper for OCP on AWS Reports."""

from django.db.models import CharField, Count, DecimalField, F, Max, Sum, Value
from django.db.models.functions import Coalesce

from api.report.provider_map import ProviderMap
from reporting.models import (OCPAWSCostLineItemDailySummary,
                              OCPAWSCostLineItemProjectDailySummary)


class OCPAWSProviderMap(ProviderMap):
    """OCP on AWS Provider Map."""

    def __init__(self, provider, report_type):
        """Constructor."""
        self._mapping = [
            {
                'provider': 'OCP_AWS',
                'alias': 'account_alias__account_alias',
                'annotations': {
                    'cluster': 'cluster_id',
                    'project': 'namespace',
                    'account': 'usage_account_id',
                    'service': 'product_code',
                    'az': 'availability_zone'
                },
                'end_date': 'usage_end',
                'filters': {
                    'project': {
                        'field': 'namespace',
                        'operation': 'icontains'
                    },
                    'cluster': [
                        {
                            'field': 'cluster_alias',
                            'operation': 'icontains',
                            'composition_key': 'cluster_filter'
                        },
                        {
                            'field': 'cluster_id',
                            'operation': 'icontains',
                            'composition_key': 'cluster_filter'
                        }
                    ],
                    'node': {
                        'field': 'node',
                        'operation': 'icontains'
                    },
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
                    'product_family': {
                        'field': 'product_family',
                        'operation': 'icontains'
                    },
                    'az': {
                        'field': 'availability_zone',
                        'operation': 'icontains'
                    },
                    'region': {
                        'field': 'region',
                        'operation': 'icontains'
                    }
                },
                'group_by_options': ['account', 'service', 'region',
                                     'cluster', 'project', 'node', 'product_family'],
                'tag_column': 'tags',
                'report_type': {
                    'costs': {
                        'aggregates': {
                            'infrastructure_cost': Sum(F('unblended_cost')),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'cost': Sum(F('unblended_cost')),
                        },
                        'annotations': {
                            'infrastructure_cost': Sum(F('unblended_cost')),
                            'derived_cost': Value(0, output_field=DecimalField()),
                            'cost': Sum(F('unblended_cost')),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD'))
                        },
                        'count': None,
                        'delta_key': {'cost': Sum(F('unblended_cost'))},
                        'filter': {},
                        'cost_units_key': 'currency_code',
                        'cost_units_fallback': 'USD',
                        'sum_columns': ['cost', 'infrastructure_cost', 'derived_cost'],
                        'default_ordering': {'cost': 'desc'},
                    },
                    'costs_by_project': {
                        'tables': {
                            'query': OCPAWSCostLineItemProjectDailySummary,
                            'total': OCPAWSCostLineItemProjectDailySummary
                        },
                        'aggregates': {
                            'infrastructure_cost': Sum('pod_cost'),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'cost': Sum('pod_cost'),
                        },
                        'annotations': {
                            'infrastructure_cost': Sum('pod_cost'),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'cost': Sum('pod_cost'),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD'))
                        },
                        'count': None,
                        'delta_key': {'cost': Sum('pod_cost')},
                        'filter': {},
                        'cost_units_key': 'currency_code',
                        'cost_units_fallback': 'USD',
                        'sum_columns': ['infrastructure_cost',
                                        'derived_cost', 'cost'],
                        'default_ordering': {'cost': 'desc'},
                    },
                    'storage': {
                        'aggregates': {
                            'infrastructure_cost': Sum(F('unblended_cost')),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'cost': Sum(F('unblended_cost')),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD')),
                            'usage': Sum(F('usage_amount')),
                            'usage_units': Coalesce(Max('unit'), Value('GB-Mo'))
                        },
                        'annotations': {
                            'infrastructure_cost': Sum(F('unblended_cost')),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'cost': Sum(F('unblended_cost')),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD')),
                            'usage': Sum(F('usage_amount')),
                            'usage_units': Coalesce(Max('unit'), Value('GB-Mo'))
                        },
                        'count': None,
                        'delta_key': {'usage': Sum('usage_amount')},
                        'filter': {
                            'field': 'product_family',
                            'operation': 'contains',
                            'parameter': 'Storage'
                        },
                        'cost_units_key': 'currency_code',
                        'cost_units_fallback': 'USD',
                        'usage_units_key': 'unit',
                        'usage_units_fallback': 'GB-Mo',
                        'sum_columns': ['usage', 'infrastructure_cost',
                                        'derived_cost', 'cost'],
                        'default_ordering': {'usage': 'desc'},
                    },
                    'storage_by_project': {
                        'tables': {
                            'query': OCPAWSCostLineItemProjectDailySummary,
                            'total': OCPAWSCostLineItemProjectDailySummary
                        },
                        'aggregates': {
                            'infrastructure_cost': Sum('pod_cost'),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'cost': Sum('pod_cost'),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD')),
                            'usage': Sum('usage_amount'),
                            'usage_units': Coalesce(Max('unit'), Value('GB-Mo'))
                        },
                        'annotations': {
                            'infrastructure_cost': Sum('pod_cost'),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'cost': Sum('pod_cost'),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD')),
                            'usage': Sum('usage_amount'),
                            'usage_units': Coalesce(Max('unit'), Value('GB-Mo'))
                        },
                        'count': None,
                        'delta_key': {'usage': Sum('usage_amount')},
                        'filter': {
                            'field': 'product_family',
                            'operation': 'contains',
                            'parameter': 'Storage'
                        },
                        'cost_units_key': 'currency_code',
                        'cost_units_fallback': 'USD',
                        'usage_units_key': 'unit',
                        'usage_units_fallback': 'GB-Mo',
                        'sum_columns': ['usage', 'cost', 'infrastructure_cost', 'derived_cost'],
                        'default_ordering': {'usage': 'desc'},
                    },
                    'instance_type': {
                        'aggregates': {
                            'infrastructure_cost': Sum(F('unblended_cost')),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'cost': Sum(F('unblended_cost')),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD')),
                            'count': Count('resource_id', distinct=True),
                            'usage': Sum(F('usage_amount')),
                            'usage_units': Coalesce(Max('unit'), Value('GB-Mo'))
                        },
                        'aggregate_key': 'usage_amount',
                        'annotations': {
                            'infrastructure_cost': Sum(F('unblended_cost')),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'cost': Sum(F('unblended_cost')),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD')),
                            'count': Count('resource_id', distinct=True),
                            'count_units': Value('instances', output_field=CharField()),
                            'usage': Sum(F('usage_amount')),
                            'usage_units': Coalesce(Max('unit'), Value('Hrs'))
                        },
                        'count': 'resource_id',
                        'delta_key': {'usage': Sum('usage_amount')},
                        'filter': {
                            'field': 'instance_type',
                            'operation': 'isnull',
                            'parameter': False
                        },
                        'group_by': ['instance_type'],
                        'cost_units_key': 'currency_code',
                        'cost_units_fallback': 'USD',
                        'usage_units_key': 'unit',
                        'usage_units_fallback': 'Hrs',
                        'count_units_fallback': 'instances',
                        'sum_columns': ['usage', 'cost', 'infrastructure_cost',
                                        'derived_cost', 'count'],
                        'default_ordering': {'usage': 'desc'},
                    },
                    'instance_type_by_project': {
                        'tables': {
                            'query': OCPAWSCostLineItemProjectDailySummary,
                            'total': OCPAWSCostLineItemProjectDailySummary
                        },
                        'aggregates': {
                            'infrastructure_cost': Sum('pod_cost'),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'cost': Sum('pod_cost'),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD')),
                            'count': Count('resource_id', distinct=True),
                            'usage': Sum('usage_amount'),
                            'usage_units': Coalesce(Max('unit'), Value('GB-Mo'))
                        },
                        'aggregate_key': 'usage_amount',
                        'annotations': {
                            'infrastructure_cost': Sum('pod_cost'),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'cost': Sum('pod_cost'),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD')),
                            'count': Count('resource_id', distinct=True),
                            'count_units': Value('instances', output_field=CharField()),
                            'usage': Sum('usage_amount'),
                            'usage_units': Coalesce(Max('unit'), Value('Hrs'))
                        },
                        'count': 'resource_id',
                        'delta_key': {'usage': Sum('usage_amount')},
                        'filter': {
                            'field': 'instance_type',
                            'operation': 'isnull',
                            'parameter': False
                        },
                        'group_by': ['instance_type'],
                        'cost_units_key': 'currency_code',
                        'cost_units_fallback': 'USD',
                        'usage_units_key': 'unit',
                        'usage_units_fallback': 'Hrs',
                        'count_units_fallback': 'instances',
                        'sum_columns': ['usage', 'cost', 'infrastructure_cost',
                                        'derived_cost', 'count'],
                        'default_ordering': {'usage': 'desc'},
                    },
                },
                'start_date': 'usage_start',
                'tables': {
                    'query': OCPAWSCostLineItemDailySummary,
                    'total': OCPAWSCostLineItemDailySummary
                },
            }
        ]
        super().__init__(provider, report_type)
