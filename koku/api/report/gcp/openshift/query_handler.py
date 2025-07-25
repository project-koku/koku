#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP Query Handling for Reports."""
import copy

from django.db.models import CharField
from django.db.models import F
from django.db.models import Value
from django.db.models.fields.json import KT
from django.db.models.functions import Coalesce
from django.db.models.functions import Concat
from django_tenants.utils import tenant_context

from api.models import Provider
from api.report.gcp.openshift.provider_map import OCPGCPProviderMap
from api.report.gcp.query_handler import GCPReportQueryHandler
from api.report.queries import is_grouped_by_project


class OCPGCPReportQueryHandler(GCPReportQueryHandler):
    """Handles report queries and responses for OCP on GCP."""

    provider = Provider.OCP_GCP

    def __init__(self, parameters):
        """Establish OCP report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._mapper = OCPGCPProviderMap(
            provider=self.provider, report_type=parameters.report_type, schema_name=parameters.tenant.schema_name
        )
        self.group_by_options = self._mapper.provider_map.get("group_by_options")
        self._limit = parameters.get_filter("limit")

        # super() needs to be called after _mapper and _limit is set
        super().__init__(parameters)
        # super() needs to be called before _get_group_by is called

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
        # { query_param: database_field_name }
        fields = self._mapper.provider_map.get("annotations")
        for q_param, db_field in fields.items():
            annotations[q_param] = F(db_field)
        group_by_fields = self._mapper.provider_map.get("group_by_annotations")
        for group_key in self._get_group_by():
            if group_by_fields.get(group_key):
                for q_param, db_field in group_by_fields[group_key].items():
                    annotations[q_param] = Concat(db_field, Value(""))
        if is_grouped_by_project(self.parameters):
            if self._category:
                annotations["project"] = Coalesce(F("cost_category__name"), F("namespace"), output_field=CharField())
            else:
                annotations["project"] = F("namespace")
        for tag_db_name, _, original_tag in self._tag_group_by:
            annotations[tag_db_name] = KT(f"{self._mapper.tag_column}__{original_tag}")
        return annotations

    def execute_query(self):  # noqa: C901
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        query_sum = self.initialize_totals()
        data = []

        with tenant_context(self.tenant):
            query = self.query_table.objects.filter(self.query_filter)
            if self.query_exclusions:
                query = query.exclude(self.query_exclusions)
            query = query.annotate(**self.annotations)
            group_by_value = self._get_group_by()

            query_group_by = ["date"] + group_by_value
            query_order_by = ["-date", self.order]

            annotations = self._mapper.report_type_map.get("annotations")
            query_data = query.values(*query_group_by).annotate(**annotations)
            if is_grouped_by_project(self.parameters):
                query_data = self._project_classification_annotation(query_data)
            if self._limit and query_data:
                query_data = self._group_by_ranks(query, query_data)
                if not self.parameters.get("order_by"):
                    # override implicit ordering when using ranked ordering.
                    query_order_by[-1] = "rank"

            if query.exists():
                aggregates = self._mapper.report_type_map.get("aggregates")
                metric_sum = query.aggregate(**aggregates)
                query_sum = {key: metric_sum.get(key) for key in aggregates}

            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)

            query_data = self.order_by(query_data, query_order_by)

            usage_units_value = self._mapper.report_type_map.get("usage_units_fallback")
            if query_data and self._mapper.usage_units_key:
                usage_units_value = query_data[0].get("usage_units")

            if self.is_csv_output:
                data = list(query_data)
            else:
                groups = copy.deepcopy(query_group_by)
                groups.remove("date")
                data = self._apply_group_by(list(query_data), groups)
                data = self._transform_data(query_group_by, 0, data)

        init_order_keys = []
        query_sum["cost_units"] = self.currency
        if self._mapper.usage_units_key and usage_units_value:
            init_order_keys = ["usage_units"]
            query_sum["usage_units"] = usage_units_value
        key_order = list(init_order_keys + list(annotations.keys()))
        ordered_total = {total_key: query_sum[total_key] for total_key in key_order if total_key in query_sum}
        ordered_total.update(query_sum)
        self._pack_data_object(ordered_total, **self._mapper.PACK_DEFINITIONS)

        self.query_sum = ordered_total
        self.query_data = data
        return self._format_query_response()
