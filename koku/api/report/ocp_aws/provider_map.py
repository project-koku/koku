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
                            'cost': Sum(
                                Coalesce(F('unblended_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum(F('unblended_cost')),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'markup_cost': Sum(
                                Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                        },
                        'annotations': {
                            # Cost is the first column in annotations so that it
                            # can reference the original database column 'markup_cost'
                            # If cost comes after the markup_cost annotaton, then
                            # Django will reference the annotated value, which is
                            # a Sum() and things will break trying to add
                            # a column with the sum of another column.
                            'cost': Sum(
                                Coalesce(F('unblended_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum(F('unblended_cost')),
                            'derived_cost': Value(0, output_field=DecimalField()),
                            'markup_cost': Sum(
                                Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD'))
                        },
                        'count': None,
                        'delta_key': {
                            'cost': Sum(
                                Coalesce(F('unblended_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            )
                        },
                        'filter': [{}],
                        'cost_units_key': 'currency_code',
                        'cost_units_fallback': 'USD',
                        'sum_columns': ['cost', 'infrastructure_cost', 'derived_cost', 'markup_cost'],
                        'default_ordering': {'cost': 'desc'},
                    },
                    'costs_by_project': {
                        'tables': {
                            'query': OCPAWSCostLineItemProjectDailySummary,
                            'total': OCPAWSCostLineItemProjectDailySummary
                        },
                        'aggregates': {
                            'cost': Sum(
                                Coalesce(F('pod_cost'), Value(0, output_field=DecimalField()))\
                                + Coalesce(F('project_markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum('pod_cost'),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'markup_cost': Sum(
                                Coalesce(F('project_markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                        },
                        'annotations': {
                            'cost': Sum(
                                Coalesce(F('pod_cost'), Value(0, output_field=DecimalField()))\
                                + Coalesce(F('project_markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum('pod_cost'),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'markup_cost': Sum(
                                Coalesce(F('project_markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD'))
                        },
                        'count': None,
                        'delta_key': {
                            'cost': Sum(
                                Coalesce(F('pod_cost'), Value(0, output_field=DecimalField()))\
                                + Coalesce(F('project_markup_cost'), Value(0, output_field=DecimalField()))
                            )
                        },
                        'filter': [{}],
                        'cost_units_key': 'currency_code',
                        'cost_units_fallback': 'USD',
                        'sum_columns': ['infrastructure_cost', 'markup_cost',
                                        'derived_cost', 'cost'],
                        'default_ordering': {'cost': 'desc'},
                    },
                    'storage': {
                        'aggregates': {
                            'cost': Sum(
                                Coalesce(F('unblended_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum(F('unblended_cost')),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'markup_cost': Sum(
                                Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD')),
                            'usage': Sum(F('usage_amount')),
                            'usage_units': Coalesce(Max('unit'), Value('GB-Mo'))
                        },
                        'annotations': {
                            'cost': Sum(
                                Coalesce(F('unblended_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum(F('unblended_cost')),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'markup_cost': Sum(
                                Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD')),
                            'usage': Sum(F('usage_amount')),
                            'usage_units': Coalesce(Max('unit'), Value('GB-Mo'))
                        },
                        'count': None,
                        'delta_key': {'usage': Sum('usage_amount')},
                        'filter': [{
                            'field': 'product_family',
                            'operation': 'contains',
                            'parameter': 'Storage'
                        }, ],
                        'cost_units_key': 'currency_code',
                        'cost_units_fallback': 'USD',
                        'usage_units_key': 'unit',
                        'usage_units_fallback': 'GB-Mo',
                        'sum_columns': ['usage', 'infrastructure_cost',
                                        'markup_cost', 'derived_cost', 'cost'],
                        'default_ordering': {'usage': 'desc'},
                    },
                    'storage_by_project': {
                        'tables': {
                            'query': OCPAWSCostLineItemProjectDailySummary,
                            'total': OCPAWSCostLineItemProjectDailySummary
                        },
                        'aggregates': {
                            'cost': Sum(
                                Coalesce(F('pod_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('project_markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum('pod_cost'),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'markup_cost': Sum(
                                Coalesce(F('project_markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD')),
                            'usage': Sum('usage_amount'),
                            'usage_units': Coalesce(Max('unit'), Value('GB-Mo'))
                        },
                        'annotations': {
                            'cost': Sum(
                                Coalesce(F('pod_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('project_markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum('pod_cost'),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'markup_cost': Sum(
                                Coalesce(F('project_markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD')),
                            'usage': Sum('usage_amount'),
                            'usage_units': Coalesce(Max('unit'), Value('GB-Mo'))
                        },
                        'count': None,
                        'delta_key': {'usage': Sum('usage_amount')},
                        'filter': [{
                            'field': 'product_family',
                            'operation': 'contains',
                            'parameter': 'Storage'
                        }, ],
                        'cost_units_key': 'currency_code',
                        'cost_units_fallback': 'USD',
                        'usage_units_key': 'unit',
                        'usage_units_fallback': 'GB-Mo',
                        'sum_columns': ['usage', 'cost', 'infrastructure_cost', 'derived_cost',
                                        'markup_cost'],
                        'default_ordering': {'usage': 'desc'},
                    },
                    'instance_type': {
                        'aggregates': {
                            'cost': Sum(
                                Coalesce(F('unblended_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum(F('unblended_cost')),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'markup_cost': Sum(
                                Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD')),
                            'count': Count('resource_id', distinct=True),
                            'usage': Sum(F('usage_amount')),
                            'usage_units': Coalesce(Max('unit'), Value('GB-Mo'))
                        },
                        'aggregate_key': 'usage_amount',
                        'annotations': {
                            'cost': Sum(
                                Coalesce(F('unblended_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum(F('unblended_cost')),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'markup_cost': Sum(
                                Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD')),
                            'count': Count('resource_id', distinct=True),
                            'count_units': Value('instances', output_field=CharField()),
                            'usage': Sum(F('usage_amount')),
                            'usage_units': Coalesce(Max('unit'), Value('Hrs'))
                        },
                        'count': 'resource_id',
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
                                        'markup_cost', 'derived_cost', 'count'],
                        'default_ordering': {'usage': 'desc'},
                    },
                    'instance_type_by_project': {
                        'tables': {
                            'query': OCPAWSCostLineItemProjectDailySummary,
                            'total': OCPAWSCostLineItemProjectDailySummary
                        },
                        'aggregates': {
                            'cost': Sum(
                                Coalesce(F('pod_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('project_markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum('pod_cost'),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'markup_cost': Sum(
                                Coalesce(F('project_markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD')),
                            'count': Count('resource_id', distinct=True),
                            'usage': Sum('usage_amount'),
                            'usage_units': Coalesce(Max('unit'), Value('GB-Mo'))
                        },
                        'aggregate_key': 'usage_amount',
                        'annotations': {
                            'cost': Sum(
                                Coalesce(F('pod_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('project_markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum('pod_cost'),
                            'derived_cost': Sum(Value(0, output_field=DecimalField())),
                            'markup_cost': Sum(
                                Coalesce(F('project_markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'cost_units': Coalesce(Max('currency_code'), Value('USD')),
                            'count': Count('resource_id', distinct=True),
                            'count_units': Value('instances', output_field=CharField()),
                            'usage': Sum('usage_amount'),
                            'usage_units': Coalesce(Max('unit'), Value('Hrs'))
                        },
                        'count': 'resource_id',
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
                                        'markup_cost', 'derived_cost', 'count'],
                        'default_ordering': {'usage': 'desc'},
                    },
                    'tags': {
                        'default_ordering': {'cost': 'desc'},
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
