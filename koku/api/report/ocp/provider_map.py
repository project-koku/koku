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

from django.db.models import CharField, DecimalField, F, Max, Sum, Value
from django.db.models.functions import Coalesce
from providers.provider_access import ProviderAccessor

from api.report.provider_map import ProviderMap
from reporting.models import OCPUsageLineItemDailySummary


class OCPProviderMap(ProviderMap):
    """OCP Provider Map."""

    def __init__(self, provider, report_type):
        """Constructor."""
        self._mapping = [
            {
                'provider': 'OCP',
                'annotations': {
                    'cluster': 'cluster_id',
                    'project': 'namespace'
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
                    'pod': {
                        'field': 'pod',
                        'operation': 'icontains'
                    },
                    'node': {
                        'field': 'node',
                        'operation': 'icontains'
                    },
                    'infrastructures': {
                        'field': 'cluster_id',
                        'operation': 'exact',
                        'custom': ProviderAccessor('OCP').infrastructure_key_list
                    },
                },
                'group_by_options': ['cluster', 'project', 'node'],
                'tag_column': 'pod_labels',
                'report_type': {
                    'costs': {
                        'tables': {
                            'query': OCPUsageLineItemDailySummary
                        },
                        'aggregates': {
                            'cost': Sum(
                                Coalesce(F('pod_charge_cpu_core_hours'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('pod_charge_memory_gigabyte_hours'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('persistentvolumeclaim_charge_gb_month'),
                                           Value(0, output_field=DecimalField()))
                                + Coalesce(F('infra_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum(F('infra_cost')),
                            'derived_cost': Sum(
                                Coalesce(F('pod_charge_cpu_core_hours'),
                                         Value(0, output_field=DecimalField()))
                                + Coalesce(F('pod_charge_memory_gigabyte_hours'),
                                           Value(0, output_field=DecimalField()))
                                + Coalesce(F('persistentvolumeclaim_charge_gb_month'),
                                           Value(0, output_field=DecimalField()))
                            ),
                            'markup_cost': Sum(
                                Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                        },
                        'default_ordering': {'cost': 'desc'},
                        'annotations': {
                            'cost': Sum(
                                Coalesce(F('pod_charge_cpu_core_hours'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('pod_charge_memory_gigabyte_hours'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('persistentvolumeclaim_charge_gb_month'),
                                           Value(0, output_field=DecimalField()))
                                + Coalesce(F('infra_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum(F('infra_cost')),
                            'derived_cost': Sum(
                                Coalesce(F('pod_charge_cpu_core_hours'),
                                         Value(0, output_field=DecimalField()))
                                + Coalesce(F('pod_charge_memory_gigabyte_hours'),
                                           Value(0, output_field=DecimalField()))
                                + Coalesce(F('persistentvolumeclaim_charge_gb_month'),
                                           Value(0, output_field=DecimalField()))
                            ),
                            'markup_cost': Sum(
                                Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'cost_units': Value('USD', output_field=CharField())
                        },
                        'capacity_aggregate': {},
                        'delta_key': {
                            'cost': Sum(
                                Coalesce(F('pod_charge_cpu_core_hours'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('pod_charge_memory_gigabyte_hours'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('persistentvolumeclaim_charge_gb_month'),
                                           Value(0, output_field=DecimalField()))
                                + Coalesce(F('infra_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                        },
                        'filter': [{}],
                        'cost_units_key': 'USD',
                        'sum_columns': ['cost', 'infrastructure_cost', 'derived_cost', 'markup_cost'],
                    },
                    'costs_by_project': {
                        'tables': {
                            'query': OCPUsageLineItemDailySummary
                        },
                        'aggregates': {
                            'cost': Sum(
                                Coalesce(F('pod_charge_cpu_core_hours'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('pod_charge_memory_gigabyte_hours'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('persistentvolumeclaim_charge_gb_month'),
                                           Value(0, output_field=DecimalField()))
                                + Coalesce(F('project_infra_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('project_markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum(F('project_infra_cost')),
                            'derived_cost': Sum(
                                Coalesce(F('pod_charge_cpu_core_hours'),
                                         Value(0, output_field=DecimalField()))
                                + Coalesce(F('pod_charge_memory_gigabyte_hours'),
                                           Value(0, output_field=DecimalField()))
                                + Coalesce(F('persistentvolumeclaim_charge_gb_month'),
                                           Value(0, output_field=DecimalField()))
                            ),
                            'markup_cost': Sum(
                                Coalesce(F('project_markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                        },
                        'default_ordering': {'cost': 'desc'},
                        'annotations': {
                            'cost': Sum(
                                Coalesce(F('pod_charge_cpu_core_hours'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('pod_charge_memory_gigabyte_hours'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('persistentvolumeclaim_charge_gb_month'),
                                           Value(0, output_field=DecimalField()))
                                + Coalesce(F('project_infra_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('project_markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'infrastructure_cost': Sum(F('project_infra_cost')),
                            'derived_cost': Sum(
                                Coalesce(F('pod_charge_cpu_core_hours'),
                                         Value(0, output_field=DecimalField()))
                                + Coalesce(F('pod_charge_memory_gigabyte_hours'),
                                           Value(0, output_field=DecimalField()))
                                + Coalesce(F('persistentvolumeclaim_charge_gb_month'),
                                           Value(0, output_field=DecimalField()))
                            ),
                            'markup_cost': Sum(
                                Coalesce(F('project_markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                            'cost_units': Value('USD', output_field=CharField())
                        },
                        'capacity_aggregate': {},
                        'delta_key': {
                            'cost': Sum(
                                Coalesce(F('pod_charge_cpu_core_hours'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('pod_charge_memory_gigabyte_hours'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('persistentvolumeclaim_charge_gb_month'),
                                           Value(0, output_field=DecimalField()))
                                + Coalesce(F('project_infra_cost'), Value(0, output_field=DecimalField()))
                                + Coalesce(F('project_markup_cost'), Value(0, output_field=DecimalField()))
                            ),
                        },
                        'filter': [{}],
                        'cost_units_key': 'USD',
                        'sum_columns': ['cost', 'infrastructure_cost', 'derived_cost', 'markup_cost'],
                    },
                    'cpu': {
                        'aggregates': {
                            'cost': Sum('pod_charge_cpu_core_hours'),
                            'usage': Sum('pod_usage_cpu_core_hours'),
                            'request': Sum('pod_request_cpu_core_hours'),
                            'limit': Sum('pod_limit_cpu_core_hours'),
                            'infrastructure_cost': Sum(Value(0, output_field=DecimalField())),
                            'derived_cost': Sum('pod_charge_cpu_core_hours'),
                        },
                        'capacity_aggregate': {
                            'capacity': Max('cluster_capacity_cpu_core_hours')
                        },
                        'default_ordering': {'usage': 'desc'},
                        'annotations': {
                            'usage': Sum('pod_usage_cpu_core_hours'),
                            'request': Sum('pod_request_cpu_core_hours'),
                            'limit': Sum('pod_limit_cpu_core_hours'),
                            'capacity': {
                                'total': Max('total_capacity_cpu_core_hours'),
                                'cluster': Max('cluster_capacity_cpu_core_hours'),
                            },
                            'cost': Sum('pod_charge_cpu_core_hours'),
                            'infrastructure_cost': Value(0, output_field=DecimalField()),
                            'derived_cost': Sum('pod_charge_cpu_core_hours'),
                            'cost_units': Value('USD', output_field=CharField()),
                            'usage_units': Value('Core-Hours', output_field=CharField())
                        },
                        'delta_key': {
                            'usage': Sum('pod_usage_cpu_core_hours'),
                            'request': Sum('pod_request_cpu_core_hours'),
                            'cost': Sum('pod_charge_cpu_core_hours')
                        },
                        'filter': [
                            {
                                'field': 'data_source',
                                'operation': 'exact',
                                'parameter': 'Pod'
                            }
                        ],
                        'cost_units_key': 'USD',
                        'usage_units_key': 'Core-Hours',
                        'sum_columns': ['usage', 'request', 'limit', 'infrastructure_cost',
                                        'derived_cost', 'cost'],
                    },
                    'memory': {
                        'aggregates': {
                            'usage': Sum('pod_usage_memory_gigabyte_hours'),
                            'request': Sum('pod_request_memory_gigabyte_hours'),
                            'limit': Sum('pod_limit_memory_gigabyte_hours'),
                            'cost': Sum('pod_charge_memory_gigabyte_hours'),
                            'infrastructure_cost': Sum(Value(0, output_field=DecimalField())),
                            'derived_cost': Sum('pod_charge_memory_gigabyte_hours'),
                        },
                        'capacity_aggregate': {
                            'capacity': Max('cluster_capacity_memory_gigabyte_hours')
                        },
                        'default_ordering': {'usage': 'desc'},
                        'annotations': {
                            'usage': Sum('pod_usage_memory_gigabyte_hours'),
                            'request': Sum('pod_request_memory_gigabyte_hours'),
                            'limit': Sum('pod_limit_memory_gigabyte_hours'),
                            'capacity': {
                                'total': Max('total_capacity_memory_gigabyte_hours'),
                                'cluster': Max('cluster_capacity_memory_gigabyte_hours'),
                            },
                            'cost': Sum('pod_charge_memory_gigabyte_hours'),
                            'infrastructure_cost': Value(0, output_field=DecimalField()),
                            'derived_cost': Sum('pod_charge_memory_gigabyte_hours'),
                            'cost_units': Value('USD', output_field=CharField()),
                            'usage_units': Value('GB-Hours', output_field=CharField())
                        },
                        'delta_key': {
                            'usage': Sum('pod_usage_memory_gigabyte_hours'),
                            'request': Sum('pod_request_memory_gigabyte_hours'),
                            'cost': Sum('pod_charge_memory_gigabyte_hours')
                        },
                        'filter': [
                            {
                                'field': 'data_source',
                                'operation': 'exact',
                                'parameter': 'Pod'
                            }
                        ],
                        'cost_units_key': 'USD',
                        'usage_units_key': 'GB-Hours',
                        'sum_columns': ['usage', 'request', 'limit', 'infrastructure_cost',
                                        'derived_cost', 'cost'],
                    },
                    'volume': {
                        'tables': {
                            'query': OCPUsageLineItemDailySummary
                        },
                        'tag_column': 'volume_labels',
                        'aggregates': {
                            'usage': Sum('persistentvolumeclaim_usage_gigabyte_months'),
                            'request': Sum('volume_request_storage_gigabyte_months'),
                            'cost': Sum('persistentvolumeclaim_charge_gb_month'),
                            'infrastructure_cost': Sum(Value(0, output_field=DecimalField())),
                            'derived_cost': Sum('persistentvolumeclaim_charge_gb_month'),
                        },
                        'capacity_aggregate': {
                            'capacity': Sum('persistentvolumeclaim_capacity_gigabyte_months')
                        },
                        'default_ordering': {'usage': 'desc'},
                        'annotations': {
                            'usage': Sum('persistentvolumeclaim_usage_gigabyte_months'),
                            'request': Sum('volume_request_storage_gigabyte_months'),
                            'capacity': {
                                'total': Sum('persistentvolumeclaim_capacity_gigabyte_months'),
                                'cluster': Sum('persistentvolumeclaim_capacity_gigabyte_months'),
                            },
                            'cost': Sum('persistentvolumeclaim_charge_gb_month'),
                            'infrastructure_cost': Value(0, output_field=DecimalField()),
                            'derived_cost': Sum('persistentvolumeclaim_charge_gb_month'),
                            'cost_units': Value('USD', output_field=CharField()),
                            'usage_units': Value('GB-Mo', output_field=CharField()),
                        },
                        'delta_key': {
                            'usage': Sum('persistentvolumeclaim_usage_gigabyte_months'),
                            'request': Sum('volume_request_storage_gigabyte_months'),
                            'cost': Sum('persistentvolumeclaim_charge_gb_month')
                        },
                        'filter': [
                            {
                                'field': 'data_source',
                                'operation': 'exact',
                                'parameter': 'Storage'
                            }
                        ],
                        'cost_units_key': 'USD',
                        'usage_units_key': 'GB-Mo',
                        'sum_columns': ['usage', 'request', 'infrastructure_cost',
                                        'derived_cost', 'cost'],
                    },
                    'tags': {
                        'default_ordering': {'cost': 'desc'},
                    },
                },
                'start_date': 'usage_start',
                'tables': {
                    'query': OCPUsageLineItemDailySummary,
                },
            },
        ]
        super().__init__(provider, report_type)
