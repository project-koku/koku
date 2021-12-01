#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""AWS Query Handling for Reports."""
import copy
import logging
import operator
from functools import reduce

from django.core.exceptions import FieldDoesNotExist
from django.db.models import F
from django.db.models import Q
from django.db.models import Value
from django.db.models.expressions import Func
from django.db.models.functions import Coalesce
from tenant_schemas.utils import tenant_context

from api.models import Provider
from api.report.aws.provider_map import AWSProviderMap
from api.report.aws.provider_map import CSV_FIELD_MAP
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
    "savingsplan_effective_cost",
    "blended_rate",
    "blended_cost",
    "tax_type",
]


class AWSReportQueryHandler(ReportQueryHandler):
    """Handles report queries and responses for AWS."""

    provider = Provider.PROVIDER_AWS
    network_services = {"AmazonVPC", "AmazonCloudFront", "AmazonRoute53", "AmazonAPIGateway"}
    database_services = {
        "AmazonRDS",
        "AmazonDynamoDB",
        "AmazonElastiCache",
        "AmazonNeptune",
        "AmazonRedshift",
        "AmazonDocumentDB",
    }

    def __init__(self, parameters):
        """Establish AWS report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        # do not override mapper if its already set
        try:
            getattr(self, "_mapper")
        except AttributeError:
            self._mapper = AWSProviderMap(
                provider=self.provider,
                report_type=parameters.report_type,
                cost_type=parameters.parameters.get("cost_type"),
            )

        self.group_by_options = self._mapper.provider_map.get("group_by_options")
        self._limit = parameters.get_filter("limit")
        self.is_csv_output = parameters.accept_type and "text/csv" in parameters.accept_type
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
                annotations[q_param] = F(db_field)
        return annotations

    def format_sub_org_results(self, query_data_results, query_data, sub_orgs_dict):  # noqa: C901
        """
        Add the sub_orgs into the overall results if grouping by org unit.

        Args:
            query_data_results: (list) list of query data results
            query_data: (list) the original query_data
            sub_orgs_dict: (dict) dictionary mapping the org_unit_names and ids

        Returns:
            (list) the overall query data results
        """
        # loop through original query data
        group_by_format_keys = [key + "s" for key in self.parameters.parameters.get("group_by").keys()]
        for each_day in query_data:
            accounts = each_day.get("accounts", [])
            # rename id/alias and add type
            for account in accounts:
                account["id"] = account.pop("account")
                account["type"] = "account"
                if group_by_format_keys:
                    for format_key in group_by_format_keys:
                        for group in account.get(format_key, []):
                            for value in group.get("values", []):
                                value["id"] = value.pop("account")
                                value["alias"] = value.pop("account_alias")
                for value in account.get("values", []):
                    value["id"] = value.pop("account")
                    value["alias"] = value.pop("account_alias")
            # rename entire structure to org_entities
            each_day["org_entities"] = each_day.pop("accounts", [])
        # now go through each sub org query
        for org_name, org_data in query_data_results.items():
            for day in org_data:
                for each_day in query_data:
                    if day["date"] == each_day["date"] and day.get("values"):
                        values = day.get("values")
                        for value in values:
                            # add id and org alias to values
                            value["id"] = sub_orgs_dict.get(org_name)[0]
                            value["alias"] = org_name
                        org_entities = each_day["org_entities"]
                        org_entities.append(
                            {
                                "id": sub_orgs_dict.get(org_name)[0],
                                "type": "organizational_unit",
                                "date": day.get("date"),
                                "values": values,
                            }
                        )
                        # now we need to do an order by cost
                        reverse = False
                        if "-cost_total" in self.order:
                            # if - then we want to order by desc
                            reverse = True
                        org_entities.sort(key=lambda e: e["values"][0]["cost"]["total"]["value"], reverse=reverse)
                        each_day["org_entities"] = org_entities

        return query_data

    def _set_csv_output_fields(self, query_data):
        for rec in query_data:
            for target, mapped in CSV_FIELD_MAP.items():
                if target in rec:
                    rec[mapped] = rec[target]
                    del rec[target]

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
        org_unit_applied = False
        csv_results = []
        group_by_param = self.parameters.parameters.get("group_by")
        ou_group_by_key = None
        for potential_key in ["org_unit_id", "or:org_unit_id"]:
            if potential_key in group_by_param:
                ou_group_by_key = potential_key
        if ou_group_by_key:
            org_unit_applied = True
            # Whenever we do a groub_by org unit, we are actually doing a group_by account
            # and filtering on the org unit. Therefore we are removing the group by org unit.
            org_unit_group_by_data = group_by_param.pop(ou_group_by_key)
            # Parent OU filters
            org_unit_objects = (
                AWSOrganizationalUnit.objects.filter(org_unit_id__in=org_unit_group_by_data)
                .filter(account_alias__isnull=True)
                .order_by("org_unit_id", "-created_timestamp")
                .distinct("org_unit_id")
            )
            # adding a group by account.
            if not self.parameters.parameters["group_by"].get("account"):
                self.parameters.parameters["group_by"]["account"] = ["*"]
                if self.access:
                    self.parameters._configure_access_params(self.parameters.caller)

            if org_unit_objects:
                sub_ou_list = []
                # Loop through parent ids to find children org units 1 level below.
                for org_unit_object in org_unit_objects:
                    sub_query = (
                        AWSOrganizationalUnit.objects.filter(level=(org_unit_object.level + 1))
                        .filter(org_unit_path__icontains=org_unit_object.org_unit_id)
                        .filter(account_alias__isnull=True)
                        .exclude(org_unit_id__in=org_unit_group_by_data)
                        .order_by("org_unit_id", "-created_timestamp")
                        .distinct("org_unit_id")
                    )
                    sub_ou_list.append(sub_query)

                # only do a union if more than one org_unit_id was passed in.
                if len(sub_ou_list) > 1:
                    sub_query_set = sub_ou_list.pop()
                    sub_ou_ids_list = sub_query_set.union(*sub_ou_list).values_list("org_unit_id", flat=True)
                    # Note: The django orm won't let you do an order_by & distinct on the union of
                    # multiple queries. The additional order_by &  distinct is essential to handle
                    # use cases like OU_005 being moved from OU_002 to OU_001.
                    sub_orgs = (
                        AWSOrganizationalUnit.objects.filter(org_unit_id__in=sub_ou_ids_list)
                        .filter(account_alias__isnull=True)
                        .order_by("org_unit_id", "-created_timestamp")
                        .distinct("org_unit_id")
                    )
                else:
                    sub_orgs = sub_ou_list[0]
                for org_object in sub_orgs:
                    sub_orgs_dict[org_object.org_unit_name] = org_object.org_unit_id, org_object.org_unit_path
            # First we need to modify the parameters to get all accounts if org unit group_by is used
            self.parameters.set_filter(org_unit_single_level=org_unit_group_by_data)
            self.query_filter = self._get_filter()

        # grab the base query
        # (without org_units this is the only query - with org_units this is the query to find the accounts)
        query_data, query_sum = self.execute_individual_query(org_unit_applied)

        # Next we want to loop through each sub_org and execute the query for it
        if org_unit_applied:
            for sub_org_name, value in sub_orgs_dict.items():
                sub_org_id, sub_org_path = value
                if self.parameters.get_filter("org_unit_id"):
                    self.parameters.parameters["filter"].pop("org_unit_id")
                if self.parameters.get_filter("org_unit_single_level"):
                    self.parameters.parameters["filter"].pop("org_unit_single_level")
                if self.parameters.parameters["group_by"].get("account"):
                    self.parameters.parameters["group_by"].pop("account")
                # only add the org_unit to the filter if the user has access
                # through RBAC so that we avoid returning a 403
                org_access = None
                if self.access:
                    org_access = self.access.get("aws.organizational_unit", {}).get("read", [])
                if org_access is None or (sub_org_id in org_access or "*" in org_access):
                    # We need need to use the sub org path here because if we use the org unit id
                    # it will grab partial data from other orgs if the org unit is moved during
                    # the report period.
                    self.parameters.set_filter(org_unit_id=[sub_org_path])
                self.query_filter = self._get_filter()
                sub_query_data, sub_query_sum = self.execute_individual_query(org_unit_applied)
                query_sum = self.total_sum(sub_query_sum, query_sum)

                # If we're processing for CSV output, then just append the results to a
                # CSV output list and ensure that id, alias, and type are filled out correctly
                if not self.is_csv_output:
                    query_data_results[sub_org_name] = sub_query_data
                else:
                    # Add the initial account query results, if not set
                    if len(csv_results) == 0:
                        csv_results = [dict(type="account", **d) for d in query_data]
                    # And extend by the org unit query results
                    # keys "account_alias" and "account_id" are used here to match the query's
                    # structure so that the CSV MAPPER can rename the proper keys as one of the
                    # final steps in CSV processing
                    csv_results.extend(
                        dict(type="organizational_unit", account_alias=sub_org_name, account=sub_org_id, **d)
                        for d in sub_query_data
                    )
        else:
            # If we're processing for CSV output, but were not processing
            # org unit, then just make the CSV result list the initial query data results
            if self.is_csv_output:
                csv_results = query_data

        if not self.is_csv_output:
            # If not CSV output and org unit was applied, then reshape the output
            # structures for the JSON serializer
            if org_unit_applied:
                query_data = self.format_sub_org_results(query_data_results, query_data, sub_orgs_dict)
        else:
            # For CSV output, if there was a limit, then sent *all* output (base + sub-org, if any)
            # to the ranked list method
            if self._limit:
                query_data = self._ranked_list(csv_results) if self._limit else csv_results
            else:
                # Otherwise, just set the output intermediate variable to the CSV results list
                query_data = csv_results

            query_data = self._set_csv_output_fields(query_data)

        # Add each of the sub_org sums to the query_sum
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
            sum_query = query.annotate(**sum_annotations).order_by()
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

    def set_access_filters(self, access, filt, filters):
        """
        Sets the access filters to ensure RBAC restrictions given the users access,
        the current filter and the filter collection
        Args:
            access (list) the list containing the users relevant access
            filt (list or dict) contains the filters that need
            filters (QueryFilterCollection) the filter collection to add the new filters to
        returns:
            None
        """
        # Note that the RBAC access for organizational units should follow the hierarchical
        # structure of the tree. Therefore, as long as the user has access to the root nodes
        # passed in by group_by[org_unit_id] then the user automatically has access to all
        # the sub orgs.
        with tenant_context(self.tenant):
            if access and "*" not in access:
                allowed_ous = (
                    AWSOrganizationalUnit.objects.filter(
                        reduce(operator.or_, (Q(org_unit_path__icontains=rbac) for rbac in access))
                    )
                    .filter(account_alias__isnull=True)
                    .order_by("org_unit_id", "-created_timestamp")
                    .distinct("org_unit_id")
                )
                if allowed_ous:
                    access = list(allowed_ous.values_list("org_unit_id", flat=True))
            if not isinstance(filt, list) and filt["field"] == "organizational_unit__org_unit_path":
                filt["field"] = "organizational_unit__org_unit_id"
        super().set_access_filters(access, filt, filters)

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
        else:
            for expected_key in expected_keys:
                if sum1.get(expected_key) and sum2.get(expected_key):
                    sum2[expected_key] = self.total_sum(sum1.get(expected_key), sum2.get(expected_key))
        return sum2

    def execute_individual_query(self, org_unit_applied=False):  # noqa: C901
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
            query_order_by.extend(self.order)  # add implicit ordering

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

            def check_if_valid_date_str(date_str):
                """Check to see if a valid date has been passed in."""
                import ciso8601

                try:
                    ciso8601.parse_datetime(date_str)
                except ValueError:
                    return False
                except TypeError:
                    return False
                return True

            query_sum = self._build_sum(query, annotations)

            if self._limit and query_data and not org_unit_applied:
                query_data = self._group_by_ranks(query, query_data)
                if not self.parameters.get("order_by"):
                    # override implicit ordering when using ranked ordering.
                    query_order_by[-1] = "rank"

            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)

            order_date = None
            for i, param in enumerate(query_order_by):
                if check_if_valid_date_str(param):
                    order_date = param
                    break
            # Remove the date order by as it is not actually used for ordering
            if order_date:

                sort_term = self._get_group_by()[0]
                query_order_by.pop(i)
                filtered_query_data = []
                for index in query_data:
                    for key, value in index.items():
                        if (key == "date") and (value == order_date):
                            filtered_query_data.append(index)
                ordered_data = self.order_by(filtered_query_data, query_order_by)
                order_of_interest = []
                for entry in ordered_data:
                    order_of_interest.append(entry.get(sort_term))
                # write a special order by function that iterates through the
                # rest of the days in query_data and puts them in the same order
                sorted_data = [item for x in order_of_interest for item in query_data if item.get(sort_term) == x]
                query_data = self.order_by(sorted_data, ["-date"])
            else:
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

            if not self.is_csv_output:
                groups = copy.deepcopy(query_group_by)
                groups.remove("date")
                data = self._apply_group_by(query_results, groups)
                data = self._transform_data(query_group_by, 0, data)
            else:
                data = query_results

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

    def _group_by_ranks(self, query, data):
        """
        AWS is special because account alias is a foreign key
        and the query needs that for rankings to work.
        """
        if "account" in self._get_group_by():
            query = query.annotate(
                special_rank=Coalesce(F(self._mapper.provider_map.get("alias")), "usage_account_id")
            )
        return super()._group_by_ranks(query, data)
