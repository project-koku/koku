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
"""Provider Mapper for Reports."""


class ProviderMap:
    """Data structure mapping between API params and DB Model names.

    The idea is that reports ought to be operating on largely similar
    data sets - counts, costs, etc. The only variable is determining which
    DB tables and fields are supplying the requested data.

    ProviderMap supplies ReportQueryHandler with the appropriate model
    references to help reduce the complexity of the ReportQueryHandler.
    """

    PACK_DEFINITIONS = {
        'cost': {
            'keys': ['cost', 'infrastructure_cost', 'derived_cost', 'markup_cost', 'monthly_cost'],
            'units': 'cost_units'
        },
        'usage': {
            'keys': ['usage', 'request', 'limit', 'capacity'],
            'units': 'usage_units'
        },
        'count': {
            'keys': ['count'],
            'units': 'count_units'
        }
    }

    def provider_data(self, provider):
        """Return provider portion of map structure."""
        for item in self._mapping:
            if provider in item.get('provider'):
                return item
        return None

    def report_type_data(self, report_type, provider):
        """Return report_type portion of map structure."""
        prov = self.provider_data(provider)
        return prov.get('report_type').get(report_type)

    def __init__(self, provider, report_type):
        """Constructor."""
        self._provider = provider
        self._report_type = report_type
        self._provider_map = self.provider_data(provider)
        self._report_type_map = self.report_type_data(report_type, provider)

        # main mapping data structure
        # this data should be considered static and read-only.
        if not getattr(self, '_mapping'):
            self._mapping = [{}]

    @property
    def count(self):
        """Return the count property."""
        return self._report_type_map.get('count')

    @property
    def provider_map(self):
        """Return the provider map property."""
        return self._provider_map

    @property
    def query_table(self):
        """Return the appropriate query table for the report type."""
        report_table = self._report_type_map.get('tables', {}).get('query')
        default = self._provider_map.get('tables').get('query')
        return report_table if report_table else default

    @property
    def report_type_map(self):
        """Return the report-type map property."""
        return self._report_type_map

    @property
    def sum_columns(self):
        """Return the sum column list for the report type."""
        return self._report_type_map.get('sum_columns')

    @property
    def tag_column(self):
        """Return the appropriate query table for the report type."""
        report_specific_column = self._report_type_map.get('tag_column')
        default = self._provider_map.get('tag_column')
        return report_specific_column if report_specific_column else default

    @property
    def cost_units_key(self):
        """Return the cost_units_key property."""
        return self._report_type_map.get('cost_units_key')

    @property
    def usage_units_key(self):
        """Return the usage_units_key property."""
        return self._report_type_map.get('usage_units_key')
