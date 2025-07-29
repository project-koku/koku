#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
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

    # WARNING: OCP overwrites the cost_groups keys to include distributed cost
    # in the query handler init
    PACK_DEFINITIONS = {
        # I structured the cost_groups in this way in order to keep the big O
        # notation the same in queries.py with only one for loop.
        "cost_groups": {
            "keys": {
                "infra_raw": {"key": "raw", "group": "infrastructure"},
                "infra_markup": {"key": "markup", "group": "infrastructure"},
                "infra_usage": {"key": "usage", "group": "infrastructure"},
                "infra_total": {"key": "total", "group": "infrastructure"},
                "sup_raw": {"key": "raw", "group": "supplementary"},
                "sup_markup": {"key": "markup", "group": "supplementary"},
                "sup_usage": {"key": "usage", "group": "supplementary"},
                "sup_total": {"key": "total", "group": "supplementary"},
                "cost_raw": {"key": "raw", "group": "cost"},
                "cost_markup": {"key": "markup", "group": "cost"},
                "cost_usage": {"key": "usage", "group": "cost"},
                "cost_total": {"key": "total", "group": "cost"},
            },
            "units": "cost_units",
        },
        "cost": {"keys": ["monthly_cost"], "units": "cost_units"},
        "usage": {"keys": ["usage", "request", "limit", "capacity"], "units": "usage_units"},
    }

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

    def __init__(self, provider, report_type, schema_name):
        """Constructor."""
        self._provider = provider
        self._report_type = report_type
        self._schema_name = schema_name
        self._provider_map = self.provider_data(provider)
        self._report_type_map = self.report_type_data(report_type, provider)

        # main mapping data structure
        # this data should be considered static and read-only.
        if not getattr(self, "_mapping"):
            self._mapping = [{}]

    @property
    def provider_map(self):
        """Return the provider map property."""
        return self._provider_map

    @property
    def query_table(self):
        """Return the appropriate query table for the report type."""
        report_table = self._report_type_map.get("tables", {}).get("query")
        default = self._provider_map.get("tables").get("query")
        return report_table or default

    @property
    def report_type_map(self):
        """Return the report-type map property."""
        return self._report_type_map

    @property
    def sum_columns(self):
        """Return the sum column list for the report type."""
        return self._report_type_map.get("sum_columns")

    @property
    def tag_column(self):
        """Return the appropriate query table for the report type."""
        report_specific_column = self._report_type_map.get("tag_column")
        default = self._provider_map.get("tag_column")
        return report_specific_column or default

    @property
    def cost_units_key(self):
        """Return the cost_units_key property."""
        return self._report_type_map.get("cost_units_key")

    @property
    def cost_units_fallback(self):
        """Return the usage_units_key property."""
        return self._report_type_map.get("cost_units_fallback")

    @property
    def usage_units_key(self):
        """Return the usage_units_key property."""
        return self._report_type_map.get("usage_units_key")
