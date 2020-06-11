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
"""AWS Query Handling for Reports."""
import copy
import logging

from django.core.exceptions import FieldDoesNotExist
from django.db.models import F
from django.db.models import Q
from django.db.models import Value
from django.db.models import Window
from django.db.models.expressions import Func
from django.db.models.functions import Coalesce
from django.db.models.functions import Concat
from django.db.models.functions import RowNumber
from tenant_schemas.utils import tenant_context

from api.models import Provider
from api.report.aws.provider_map import AWSProviderMap
from api.report.queries import ReportQueryHandler
from reporting.provider.aws.models import AWSOrganizationalUnit

LOG = logging.getLogger(__name__)

EXPORT_COLUMNS = [
    "cost_entry_id",
    "cost_entry_bill_id",
    "cost_entry_product_id",
    "cost_entry_pricing_id",
    "cost_entry_reservation_id",
    "tags",
    "invoice_id",
    "line_item_type",
    "usage_account_id",
    "usage_start",
    "usage_end",
    "product_code",
    "usage_type",
    "operation",
    "availability_zone",
    "usage_amount",
    "normalization_factor",
    "normalized_usage_amount",
    "currency_code",
    "unblended_rate",
    "unblended_cost",
    "blended_rate",
    "blended_cost",
    "tax_type",
]


class AWSReportQueryHandler(ReportQueryHandler):
    """Handles report queries and responses for AWS."""

    provider = Provider.PROVIDER_AWS

    def __init__(self, parameters):
        """Establish AWS report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        # do not override mapper if its already set
        try:
            getattr(self, "_mapper")
        except AttributeError:
            self._mapper = AWSProviderMap(provider=self.provider, report_type=parameters.report_type)

        self.group_by_options = self._mapper.provider_map.get("group_by_options")
        self._limit = parameters.get_filter("limit")

        # super() needs to be called after _mapper and _limit is set
        super().__init__(parameters)

    @property
    def annotations(self):
        """Create dictionary for query annotations.

        Returns:
            (Dict): query annotations dictionary

        """
        units_fallback = self._mapper.report_type_map.get("cost_units_fallback")
        annotations = {
            "date": self.date_trunc("usage_start"),
            "cost_units": Coalesce(self._mapper.cost_units_key, Value(units_fallback)),
        }
        if self._mapper.usage_units_key:
            units_fallback = self._mapper.report_type_map.get("usage_units_fallback")
            annotations["usage_units"] = Coalesce(self._mapper.usage_units_key, Value(units_fallback))
        # { query_param: database_field_name }
        fields = self._mapper.provider_map.get("annotations")
        prefix_removed_parameters_list = list(
            map(
                lambda x: x if ":" not in x else x.split(":", maxsplit=1)[1],
                self.parameters.get("group_by", {}).keys(),
            )
        )
        for q_param, db_field in fields.items():
            if q_param in prefix_removed_parameters_list:
                annotations[q_param] = Concat(db_field, Value(""))
        return annotations

    @property
    def query_table(self):
        """Return the database table to query against."""
        query_table = self._mapper.query_table
        report_type = self.parameters.report_type
        report_group = "default"

        excluded_filters = {"time_scope_value", "time_scope_units", "resolution", "limit", "offset"}
        filter_keys = set(self.parameters.get("filter", {}).keys())
        filter_keys = filter_keys.difference(excluded_filters)
        group_by_keys = list(self.parameters.get("group_by", {}).keys())

        # If grouping by more than 1 field, we default to the daily summary table
        if len(group_by_keys) > 1:
            return query_table
        if len(filter_keys) > 1:
            return query_table
        # If filtering on a different field than grouping by, we default to the daily summary table
        if group_by_keys and len(filter_keys.difference(group_by_keys)) != 0:
            return query_table

        # Special Casess for Network and Database Cards in the UI
        service_filter = set(self.parameters.get("filter", {}).get("service", []))
        network_services = ["AmazonVPC", "AmazonCloudFront", "AmazonRoute53", "AmazonAPIGateway"]
        database_services = [
            "AmazonRDS",
            "AmazonDynamoDB",
            "AmazonElastiCache",
            "AmazonNeptune",
            "AmazonRedshift",
            "AmazonDocumentDB",
        ]
        if report_type == "costs" and service_filter and not service_filter.difference(network_services):
            report_type = "network"
        elif report_type == "costs" and service_filter and not service_filter.difference(database_services):
            report_type = "database"

        if group_by_keys:
            report_group = group_by_keys[0]
        elif filter_keys and not group_by_keys:
            report_group = list(filter_keys)[0]
        try:
            query_table = self._mapper.views[report_type][report_group]
        except KeyError:
            msg = f"{report_group} for {report_type} has no entry in views. Using the default."
            LOG.warning(msg)
        return query_table

    def format_sub_org_results(self, query_data_results, query_data, sub_orgs_dict):
        """
        Add the sub_orgs into the overall results if grouping by org unit.

        Args:
            query_data_results: (list) list of query data results
            query_data: (list) the original query_data
            sub_orgs_dict: (dict) dictionary mapping the org_unit_names and ids

        Returns:
            (list) the overall query data results
        """
        for org_name, org_data in query_data_results.items():
            for day in org_data:
                for each_day in query_data:
                    if day["date"] == each_day["date"]:
                        if day.get("values"):
                            each_day["sub_orgs"].append(
                                {
                                    "org_unit_name": org_name,
                                    "org_unit_id": sub_orgs_dict.get(org_name),
                                    "date": day.get("date"),
                                    "values": day.get("values"),
                                }
                            )
        return query_data

    def execute_query(self):  # noqa: C901
        """Execute each query needed to return the results.

        If grouping by org_unit_id, a query will be executed to
        obtain the account results, and each sub_org results.
        Else it will return the original query.
        """
        original_filters = copy.deepcopy(self.parameters.parameters.get("filter"))
        sub_orgs_dict = {}
        query_data_results = {}
        query_sum_results = []
        org_unit_applied = False
        if "org_unit_id" in self.parameters.parameters.get("group_by"):
            org_unit_applied = True
            # remove the org unit and add in group by account
            org_unit_group_by_data = self.parameters.parameters.get("group_by").pop("org_unit_id")
            if not self.parameters.parameters["group_by"].get("account"):
                self.parameters.parameters["group_by"]["account"] = ["*"]
                if self.access:
                    self.parameters._configure_access_params(self.parameters.caller)

            # look up the org_unit_object so that we can get the level
            org_unit_object = (
                AWSOrganizationalUnit.objects.filter(org_unit_id=org_unit_group_by_data[0])
                .filter(account_alias__isnull=True)
                .first()
            )
            if org_unit_object:
                sub_orgs = list(
                    set(
                        AWSOrganizationalUnit.objects.filter(level=(org_unit_object.level + 1))
                        .filter(org_unit_path__icontains=org_unit_object.org_unit_id)
                        .filter(account_alias__isnull=True)
                    )
                )
                for org_object in sub_orgs:
                    sub_orgs_dict[org_object.org_unit_name] = org_object.org_unit_id
            # First we need to modify the parameters to get all accounts if org unit group_by is used
            self.parameters.parameters["filter"]["org_unit_id"] = org_unit_group_by_data
            self.query_filter = self._get_filter()
        # grab the base query
        # (without org_units this is the only query - with org_units this is the query to find the accounts)
        query_data, query_sum = self.execute_individual_query()
        # Next we want to loop through each sub_org and execute the query for it
        for sub_org_name, sub_org_id in sub_orgs_dict.items():
            if self.parameters.parameters["group_by"].get("account"):
                self.parameters.parameters["group_by"].pop("account")
            # only add the org_unit to the filter if the user has access
            # through RBAC so that we avoid returning a 403
            org_access = None
            if self.access:
                org_access = self.access.get("aws.organizational_unit", {}).get("read", [])
            if org_access is None or (sub_org_id in org_access or "*" in org_access):
                self.parameters.parameters["filter"]["org_unit_id"] = [sub_org_id]
            self.query_filter = self._get_filter()
            sub_query_data, sub_query_sum = self.execute_individual_query()
            query_data_results[sub_org_name] = sub_query_data
            query_sum_results.append(sub_query_sum)
        # Add the sub_org results to the query_data
        if org_unit_applied:
            for day in query_data:
                day["sub_orgs"] = []
        if query_data_results:
            query_data = self.format_sub_org_results(query_data_results, query_data, sub_orgs_dict)
        # Add each of the sub_org sums to the query_sum
        if query_sum_results:
            for sub_query in query_sum_results:
                query_sum = self.total_sum(sub_query, query_sum)
        self.query_data = query_data
        self.query_sum = query_sum

        # reset to the original query filters
        self.parameters.parameters["filter"] = original_filters
        return self._format_query_response()

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

    def _build_sum(self, query, annotations):
        """Build the sum results for the query."""
        sum_units = {}

        query_sum = self.initialize_totals()
        if not self.parameters.parameters.get("compute_count"):
            query_sum.pop("count", None)

        cost_units_fallback = self._mapper.report_type_map.get("cost_units_fallback")
        usage_units_fallback = self._mapper.report_type_map.get("usage_units_fallback")
        count_units_fallback = self._mapper.report_type_map.get("count_units_fallback")
        if query.exists():
            sum_annotations = {"cost_units": Coalesce(self._mapper.cost_units_key, Value(cost_units_fallback))}
            if self._mapper.usage_units_key:
                units_fallback = self._mapper.report_type_map.get("usage_units_fallback")
                sum_annotations["usage_units"] = Coalesce(self._mapper.usage_units_key, Value(units_fallback))
            sum_query = query.annotate(**sum_annotations)
            units_value = sum_query.values("cost_units").first().get("cost_units", cost_units_fallback)
            sum_units = {"cost_units": units_value}
            if self._mapper.usage_units_key:
                units_value = sum_query.values("usage_units").first().get("usage_units", usage_units_fallback)
                sum_units["usage_units"] = units_value
            if annotations.get("count_units"):
                sum_units["count_units"] = count_units_fallback
            query_sum = self.calculate_total(**sum_units)
        else:
            sum_units["cost_units"] = cost_units_fallback
            if annotations.get("count_units"):
                sum_units["count_units"] = count_units_fallback
            if annotations.get("usage_units"):
                sum_units["usage_units"] = usage_units_fallback
            query_sum.update(sum_units)
            self._pack_data_object(query_sum, **self._mapper.PACK_DEFINITIONS)
        return query_sum

    def _get_associated_tags(self, query_table, base_query_filters):  # noqa: C901
        """
        Query the reporting_awscostentrylineitem_daily_summary for existence of associated
        tags grouped by the account.

        Args:
            query_table (django.db.model) : Table containing the data against which we want to check for tags
            base_query_filters (django.db.model.Q) : Query filters to apply to table arg

        Returns:
            dict : {account (str): tags_exist(bool)}
        """

        def __resolve_op(op_str):
            """
            Resolve a django lookup op to a PostgreSQL operator

            Args:
                op_str (str) : django field lookup operator string

            Returns:
                str : Translated PostgreSQL operator
            """
            op_map = {
                None: "=",
                "": "=",
                "lt": "<",
                "lte": "<=",
                "gt": ">",
                "gte": ">=",
                "contains": "like",
                "icontains": "like",
                "startswith": "like",
                "istartswith": "like",
                "endswith": "like",
                "iendswith": "like",
            }

            return op_map[op_str]

        def __resolve_conditions(condition, alias="t", where=None, values=None):
            """
            Resolve a Q object to a PostgreSQL where clause condition string

            Args:
                condition (django.db.models.Q) Filters for the query
                alias (str) : Table alias (set by the calling function)
                where (None/List): Used for recursive calls only.
                values (None/List): Used for recursive calls only.

            Returns:
                dict : Result of query. On error, a log message is written and an empty dict is returned
            """
            if where is None:
                where = []
            if values is None:
                values = []

            for cond in condition.children:
                if isinstance(cond, Q):
                    __resolve_conditions(cond, alias, where, values)
                else:
                    conditional_parts = cond[0].split("__")
                    cast = f"::{conditional_parts[1]}" if len(conditional_parts) > 2 else ""
                    dj_op = conditional_parts[-1]
                    op = __resolve_op(dj_op) if len(conditional_parts) > 1 else __resolve_op(None)
                    col = (
                        f"UPPER({alias}.{conditional_parts[0]})"
                        if dj_op in ("icontains", "istartswith", "iendswith")
                        else f"{alias}.{conditional_parts[0]}"
                    )
                    values.append(
                        f"%{str(cond[1]).upper() if dj_op.startswith('i') else cond[1]}%"
                        if dj_op.endswith("contains")
                        else f"%{str(cond[1]).upper() if dj_op.startswith('i') else cond[1]}"
                        if dj_op.endswith("startswith")
                        else f"{str(cond[1]).upper() if dj_op.startswith('i') else cond[1]}%"
                        if dj_op.endswith("endswith")
                        else cond[1]
                    )
                    where.append(f" {'not ' if condition.negated else ''}{col}{cast} {op} %s{cast} ")

            return f"( {condition.connector.join(where)} )", values

        # Test the table to see if we can link to the daily summary table for tags
        try:
            _ = query_table._meta.get_field("usage_account_id")
            _ = query_table._meta.get_field("account_alias_id")
        except FieldDoesNotExist:
            return {}
        else:
            aws_tags_daily_summary_table = "reporting_awscostentrylineitem_daily_summary"
            # If the select table is not the above table, we need to join it to the above table
            # as it is the table containing the tag data
            if query_table._meta.db_table != aws_tags_daily_summary_table:
                join_table = f"""
  join {query_table._meta.db_table} as "b"
    on b.usage_account_id = t.usage_account_id
"""
            else:
                join_table = ""

            where_clause, values = __resolve_conditions(
                base_query_filters, "b" if query_table._meta.db_table != aws_tags_daily_summary_table else "t"
            )

            # Django ORM was producing inefficient and incorrect SQL for the query using this expression.
            # Therefore, at this time, the query will be written out until we can correct the ORM issue.
            sql = f"""
select coalesce(raa.account_alias, t.usage_account_id)::text as "account",
       sum((coalesce(t.tags, '{{}}'::jsonb) <> '{{}}'::jsonb)::boolean::int)::int as "tags_exist_sum"
  from {aws_tags_daily_summary_table} as "t"{join_table}
  left
  join reporting_awsaccountalias as "raa"
    on raa.id = t.account_alias_id
 where {where_clause}
 group
    by "account" ;"""
            # Saving these in case we need them
            # LOG.debug(f"AWS TAG CHECK QUERY: {sql}")
            # LOG.debug(f"AWS_TAG CHECK QUERY VALUES: {values}")

            from django.db import connection

            try:
                with connection.cursor() as cur:
                    cur.execute(sql, values)
                    res = {rec[0]: bool(rec[1]) for rec in cur}
            except Exception as e:
                LOG.error(e)
                res = {}

            return res

    def total_sum(self, sum1, sum2):  # noqa: C901
        """
        Given two sums, add the values of identical keys.
        Args:
            sum1 (Dict) the sum we are adding
            sum2 (Dict) the original sum to add to
        Returns:
            (Dict): the sum result
        """
        expected_keys = list(sum1)
        if "value" in expected_keys:
            sum2["value"] = sum1["value"] + sum2["value"]
            return sum2
        else:
            for expected_key in expected_keys:
                if sum1.get(expected_key) and sum2.get(expected_key):
                    sum2[expected_key] = self.total_sum(sum1.get(expected_key), sum2.get(expected_key))
            return sum2

    def execute_individual_query(self):  # noqa: C901
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        data = []

        with tenant_context(self.tenant):
            query_table = self.query_table
            LOG.debug(f"Using query table: {query_table}")
            tag_results = None
            query = query_table.objects.filter(self.query_filter)
            query_data = query.annotate(**self.annotations)
            query_group_by = ["date"] + self._get_group_by()
            query_order_by = ["-date"]
            query_order_by.extend([self.order])

            annotations = copy.deepcopy(self._mapper.report_type_map.get("annotations", {}))
            if not self.parameters.parameters.get("compute_count"):
                # Query parameter indicates count should be removed from DB queries
                annotations.pop("count", None)
                annotations.pop("count_units", None)

            query_data = query_data.values(*query_group_by).annotate(**annotations)

            if "account" in query_group_by:
                query_data = query_data.annotate(
                    account_alias=Coalesce(F(self._mapper.provider_map.get("alias")), "usage_account_id")
                )

                if self.parameters.parameters.get("check_tags"):
                    tag_results = self._get_associated_tags(query_table, self.query_filter)

            query_sum = self._build_sum(query, annotations)

            if self._limit:
                rank_order = getattr(F(self.order_field), self.order_direction)()
                rank_by_total = Window(expression=RowNumber(), partition_by=F("date"), order_by=rank_order)
                query_data = query_data.annotate(rank=rank_by_total)
                query_order_by.insert(1, "rank")
                query_data = self._ranked_list(query_data)

            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)

            is_csv_output = self.parameters.accept_type and "text/csv" in self.parameters.accept_type

            query_data = self.order_by(query_data, query_order_by)

            # Fetch the data (returning list(dict))
            query_results = list(query_data)

            # Resolve tag exists for unique account returned
            # if tag_results is not Falsey
            # Append the flag to the query result for the report
            if tag_results is not None:
                # Add the tag results to the report query result dicts
                for res in query_results:
                    res["tags_exist"] = tag_results.get(res["account_alias"], False)

            if is_csv_output:
                if self._limit:
                    data = self._ranked_list(query_results)
                else:
                    data = query_results
            else:
                groups = copy.deepcopy(query_group_by)
                groups.remove("date")
                data = self._apply_group_by(query_results, groups)
                data = self._transform_data(query_group_by, 0, data)

        key_order = list(["units"] + list(annotations.keys()))
        ordered_total = {total_key: query_sum[total_key] for total_key in key_order if total_key in query_sum}
        ordered_total.update(query_sum)

        query_sum = ordered_total
        query_data = data
        return query_data, query_sum

    def calculate_total(self, **units):
        """Calculate aggregated totals for the query.

        Args:
            units (dict): The units dictionary

        Returns:
            (dict) The aggregated totals for the query

        """
        query_group_by = ["date"] + self._get_group_by()
        query = self.query_table.objects.filter(self.query_filter)
        query_data = query.annotate(**self.annotations)
        query_data = query_data.values(*query_group_by)

        aggregates = copy.deepcopy(self._mapper.report_type_map.get("aggregates", {}))
        if not self.parameters.parameters.get("compute_count"):
            # Query parameter indicates count should be removed from DB queries
            aggregates.pop("count", None)

        counts = None

        if "count" in aggregates:
            resource_ids = (
                query_data.annotate(resource_id=Func(F("resource_ids"), function="unnest"))
                .values_list("resource_id", flat=True)
                .distinct()
            )
            counts = len(resource_ids)

        total_query = query.aggregate(**aggregates)
        for unit_key, unit_value in units.items():
            total_query[unit_key] = unit_value

        if counts:
            total_query["count"] = counts
        self._pack_data_object(total_query, **self._mapper.PACK_DEFINITIONS)

        return total_query
