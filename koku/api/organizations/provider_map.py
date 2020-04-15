#
# Copyright 2020 Red Hat, Inc.
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
"""Provider Mapper for AWS Organizations."""


class ProviderMap:
    """Data structure mapping between API params and DB Model names.

    The idea is that reports ought to be operating on largely similar
    data sets - counts, costs, etc. The only variable is determining which
    DB tables and fields are supplying the requested data.

    ProviderMap supplies ReportQueryHandler with the appropriate model
    references to help reduce the complexity of the ReportQueryHandler.
    """

    def provider_data(self, provider):
        """Return provider portion of map structure."""
        for item in self._mapping:
            if provider in item.get("provider"):
                return item
        return None

    def report_type_data(self, report_type, provider):
        """Return report_type portion of map structure."""
        prov = self.provider_data(provider)
        return prov.get("report_type").get(report_type)

    def __init__(self, provider, report_type):
        """Constructor."""
        self._provider = provider
        self._report_type = report_type
        self._provider_map = self.provider_data(provider)
        self._report_type_map = self.report_type_data(report_type, provider)

        # main mapping data structure
        # this data should be considered static and read-only.
        if not getattr(self, "_mapping"):
            self._mapping = [{}]
