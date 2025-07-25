#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""GCP Query Handling for Reports."""
import copy

from django.db.models import CharField
from django.db.models import F
from django.db.models import Value
from django.db.models.fields.json import KT
from django.db.models.functions import Coalesce
from django.db.models.functions import Concat
from django_tenants.utils import tenant_context

from api.models import Provider
from api.report.gcp.provider_map import GCPProviderMap
from api.report.queries import ReportQueryHandler


class GCPReportQueryHandler(ReportQueryHandler):
    """Handles report queries and responses for GCP."""

    provider = Provider.PROVIDER_GCP

    network_services = {
        "Network",
        "VPC",
        "Firewall",
        "Route",
        "IP",
        "DNS",
        "CDN",
        "NAT",
        "Traffic Director",
        "Service Discovery",
        "Cloud Domains",
        "Private Service Connect",
        "Cloud Armor",
    }

    database_services = {"SQL", "Spanner", "Bigtable", "Firestore", "Firebase", "Memorystore", "MongoDB"}

    def __init__(self, parameters):
        """Establish GCP report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        # do not override mapper if its already set
        try:
            getattr(self, "_mapper")
        except AttributeError:
            self._mapper = GCPProviderMap(
                provider=self.provider, report_type=parameters.report_type, schema_name=parameters.tenant.schema_name
            )

        self.group_by_options = self._mapper.provider_map.get("group_by_options")
        self._limit = parameters.get_filter("limit")
        self.group_by_alias = {"service": "service_alias", "gcp_project": "project_name"}

        # We need to overwrite the pack keys here to include the credit
        # dictionary in the endpoint returns.
        gcp_pack_keys = {
            "infra_raw": {"key": "raw", "group": "infrastructure"},
            "infra_markup": {"key": "markup", "group": "infrastructure"},
            "infra_usage": {"key": "usage", "group": "infrastructure"},
            "infra_credit": {"key": "credit", "group": "infrastructure"},
            "infra_total": {"key": "total", "group": "infrastructure"},
            "sup_raw": {"key": "raw", "group": "supplementary"},
            "sup_markup": {"key": "markup", "group": "supplementary"},
            "sup_usage": {"key": "usage", "group": "supplementary"},
            "sup_credit": {"key": "credit", "group": "supplementary"},
            "sup_total": {"key": "total", "group": "supplementary"},
            "cost_raw": {"key": "raw", "group": "cost"},
            "cost_markup": {"key": "markup", "group": "cost"},
            "cost_usage": {"key": "usage", "group": "cost"},
            "cost_credit": {"key": "credit", "group": "cost"},
            "cost_total": {"key": "total", "group": "cost"},
        }
        gcp_pack_definitions = copy.deepcopy(self._mapper.PACK_DEFINITIONS)
        gcp_pack_definitions["cost_groups"]["keys"] = gcp_pack_keys

        # super() needs to be called after _mapper and _limit is set
        super().__init__(parameters)
        self._mapper.PACK_DEFINITIONS = gcp_pack_definitions

    @property
    def annotations(self):
        """Create dictionary for query annotations.

        Returns:
            (Dict): query annotations dictionary

        """
        annotations = {
            "date": self.date_trunc("usage_start"),
            # this currency is used by the provider map to populate the correct currency value
            "currency_annotation": Value(self.currency, output_field=CharField()),
            **self.exchange_rate_annotation_dict,
        }
        if self._mapper.usage_units_key:
            units_fallback = self._mapper.report_type_map.get("usage_units_fallback")
            annotations["usage_units"] = Coalesce(self._mapper.usage_units_key, Value(units_fallback))
        fields = self._mapper.provider_map.get("annotations")
        for q_param, db_field in fields.items():
            annotations[q_param] = Concat(db_field, Value(""))
        group_by_fields = self._mapper.provider_map.get("group_by_annotations")
        for group_key in self._get_group_by():
            if group_by_fields.get(group_key):
                for q_param, db_field in group_by_fields[group_key].items():
                    annotations[q_param] = Concat(db_field, Value(""))
        tags = self.get_tag_group_by_keys()
        for i, t in enumerate(tags):
            annotations[f"tag_{i}"] = KT(f"{self._mapper.tag_column}__{t.split('tag:', maxsplit=1)[-1]}")

        return annotations

    def _format_query_response(self):
        """Format the query response with data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        output = self._initialize_response_output(self.parameters)
        output["data"] = self.query_data
        output["total"] = self.query_sum

        if self._delta:
            output["delta"] = self.query_delta

        return output

    def _build_sum(self, query):
        """Build the sum results for the query."""
        sum_units = {}
        query_sum = self.initialize_totals()

        usage_units_fallback = self._mapper.report_type_map.get("usage_units_fallback")

        if query.exists():
            sum_annotations = {
                "cost_units": Coalesce(self._mapper.cost_units_key, Value(self._mapper.cost_units_fallback))
            }
            if self._mapper.usage_units_key:
                units_fallback = self._mapper.report_type_map.get("usage_units_fallback")
                sum_annotations["usage_units"] = Coalesce(self._mapper.usage_units_key, Value(units_fallback))
            sum_query = query.annotate(**sum_annotations).order_by()

            units_value = self.currency
            sum_units = {"cost_units": units_value}
            if self._mapper.usage_units_key:
                units_value = sum_query.values("usage_units").first().get("usage_units", usage_units_fallback)
                sum_units["usage_units"] = units_value

            query_sum = self.calculate_total(**sum_units)
        else:
            sum_units["cost_units"] = self.currency
            if self._mapper.report_type_map.get("annotations", {}).get("usage_units"):
                sum_units["usage_units"] = usage_units_fallback
            query_sum.update(sum_units)
            self._pack_data_object(query_sum, **self._mapper.PACK_DEFINITIONS)
        return query_sum

    def execute_query(self):  # noqa: C901
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        data = []

        with tenant_context(self.tenant):
            query = self.query_table.objects.filter(self.query_filter)
            if self.query_exclusions:
                query = query.exclude(self.query_exclusions)
            query = query.annotate(**self.annotations)

            query_group_by = ["date"] + self._get_group_by()
            query_order_by = ["-date", self.order]

            annotations = self._mapper.report_type_map.get("annotations")
            for alias_key, alias_value in self.group_by_alias.items():
                if alias_key in query_group_by:
                    annotations[f"{alias_key}_alias"] = F(alias_value)
            query_data = query.values(*query_group_by).annotate(**annotations)
            query_sum = self._build_sum(query)

            if self._limit:
                query_data = self._group_by_ranks(query, query_data)
                if not self.parameters.get("order_by"):
                    # override implicit ordering when using ranked ordering.
                    query_order_by[-1] = "rank"

            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)

            query_data = self.order_by(query_data, query_order_by)

            if self.is_csv_output:
                data = list(query_data)
            else:
                groups = copy.deepcopy(query_group_by)
                groups.remove("date")
                data = self._apply_group_by(list(query_data), groups)
                data = self._transform_data(query_group_by, 0, data)

        key_order = list(["units"] + list(annotations.keys()))
        ordered_total = {total_key: query_sum[total_key] for total_key in key_order if total_key in query_sum}
        ordered_total.update(query_sum)

        self.query_sum = ordered_total
        self.query_data = data
        return self._format_query_response()

    def calculate_total(self, **units):
        """Calculate aggregated totals for the query.

        Args:
            units (dict): The units dictionary

        Returns:
            (dict) The aggregated totals for the query

        """
        query = self.query_table.objects.filter(self.query_filter)
        if self.query_exclusions:
            query = query.exclude(self.query_exclusions)
        query = query.annotate(**self.annotations)
        aggregates = self._mapper.report_type_map.get("aggregates")

        total_query = query.aggregate(**aggregates)
        for unit_key, unit_value in units.items():
            total_query[unit_key] = unit_value

        self._pack_data_object(total_query, **self._mapper.PACK_DEFINITIONS)

        return total_query
