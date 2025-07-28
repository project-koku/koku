#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""AWS Query Handling for Reports."""
import copy
import logging
import operator
from functools import reduce

from django.db.models import CharField
from django.db.models import F
from django.db.models import Q
from django.db.models import Value
from django.db.models.fields.json import KT
from django.db.models.functions import Coalesce
from django_tenants.utils import tenant_context

from api.models import Provider
from api.report.aws.provider_map import AWSProviderMap
from api.report.aws.provider_map import CSV_FIELD_MAP
from api.report.constants import AWS_CATEGORY_PREFIX
from api.report.constants import AWS_MARKUP_COST
from api.report.queries import ReportQueryHandler
from api.report.queries import strip_prefix
from reporting.provider.aws.models import AWSEnabledCategoryKeys
from reporting.provider.aws.models import AWSOrganizationalUnit

LOG = logging.getLogger(__name__)


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
            kwargs = {
                "provider": self.provider,
                "report_type": parameters.report_type,
                "schema_name": parameters.tenant.schema_name,
                "cost_type": parameters.cost_type,
            }
            if markup_cost := AWS_MARKUP_COST.get(parameters.cost_type):
                kwargs["markup_cost"] = markup_cost

            self._mapper = AWSProviderMap(**kwargs)

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
        annotations = {
            "date": self.date_trunc("usage_start"),
            # this currency is used by the provider map to populate the correct currency value
            "currency_annotation": Value(self.currency, output_field=CharField()),
            **self.exchange_rate_annotation_dict,
        }
        if self._mapper.usage_units_key:
            units_fallback = self._mapper.report_type_map.get("usage_units_fallback")
            annotations["usage_units"] = Coalesce(self._mapper.usage_units_key, Value(units_fallback))
        # { query_param: database_field_name }
        fields = self._mapper.provider_map.get("annotations")
        prefix_removed_parameters_list = list(
            x.split(":", maxsplit=1)[-1] for x in self.parameters.get("group_by", {}).keys()
        )
        for param in prefix_removed_parameters_list:
            if db_field := fields.get(param):
                annotations[param] = F(db_field)

        if hasattr(self._mapper, "aws_category_column"):
            for cat_db_name, _, original_cat in self._aws_category_group_by:
                annotations[cat_db_name] = KT(f"{self._mapper.aws_category_column}__{original_cat}")
        for tag_db_name, _, original_tag in self._tag_group_by:
            annotations[tag_db_name] = KT(f"{self._mapper.tag_column}__{original_tag}")

        return annotations

    def _contains_disabled_aws_category_keys(self):
        """
        Checks to see if aws_category passed in a disabled key.
        """
        if not self._aws_category:
            return False
        values = {strip_prefix(category, AWS_CATEGORY_PREFIX) for category in self._aws_category}
        with tenant_context(self.tenant):
            enabled = set(AWSEnabledCategoryKeys.objects.values_list("key", flat=True).filter(enabled=True).distinct())
            if values - enabled:
                self.query_data = []
                query_sum = self._build_sum(self.query_table.objects.none(), {})
                self.query_sum = self._pack_data_object(query_sum, **self._mapper.PACK_DEFINITIONS)
                return True
        return False

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
        if self._contains_disabled_aws_category_keys():
            return self._format_query_response()

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

            # adding a group by account.
            if not self.parameters.parameters["group_by"].get("account"):
                self.parameters.parameters["group_by"]["account"] = ["*"]
                if self.access:
                    self.parameters._configure_access_params(self.parameters.caller)

            sub_orgs = self._get_sub_org_units(org_unit_list=org_unit_group_by_data)
            if sub_orgs and len(sub_orgs) > 0:
                for org_object in sub_orgs:
                    sub_orgs_dict[org_object.org_unit_name] = org_object.org_unit_id, org_object.org_unit_path
            # First we need to modify the parameters to get all accounts if org unit group_by is used
            self.parameters.set_filter(org_unit_single_level=org_unit_group_by_data)
            self.query_filter = self._get_filter()

        acc_group_by_key = None
        filters = self.parameters.get("filter", {})
        if "account" in group_by_param and "org_unit_id" in filters:
            # When we filter on org_unit and group_by an account outside that org_unit
            # we are actually getting data from the org unit and the account
            #  as long as the user has access to both the account and org unit
            acc_group_by_key = "account"
            acc_group_by_data = group_by_param.get(acc_group_by_key)
            org_unit_list = filters.get("org_unit_id")
            self.parameters.parameters["access"]["org_unit_id"] = org_unit_list
            self.parameters.parameters["access"]["account"] = acc_group_by_data

            # Use OR operator
            self.parameters.set("aws_use_or_operator", True)
            self.parameters._configure_access_params(self.parameters.caller)
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
                sub_org_unit_ids = []
                if self.access:
                    org_access = self.access.get("aws.organizational_unit", {}).get("read", [])
                    for org_unit in org_access:
                        sub_org_unit_ids.append(org_unit)

                    # get all sub org units
                    sub_orgs = self._get_sub_org_units(org_access)
                    if sub_orgs and len(sub_orgs) > 0:
                        for org_object in sub_orgs:
                            sub_org_unit_ids.append(org_object.org_unit_id)

                if org_access is None or (sub_org_id in sub_org_unit_ids or "*" in org_access):
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

        if not self.is_csv_output and org_unit_applied:
            # If not CSV output and org unit was applied, then reshape the output
            # structures for the JSON serializer
            query_data = self.format_sub_org_results(query_data_results, query_data, sub_orgs_dict)
        elif self._report_type == "ec2_compute":
            # Handle formating EC2 compute response
            query_data = self.format_ec2_response(query_data)
        else:
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

        usage_units_fallback = self._mapper.report_type_map.get("usage_units_fallback")
        if query.exists():
            sum_annotations = {
                "cost_units": Coalesce(self._mapper.cost_units_key, Value(self._mapper.cost_units_fallback))
            }
            if self._mapper.usage_units_key:
                units_fallback = self._mapper.report_type_map.get("usage_units_fallback")
                sum_annotations["usage_units"] = Coalesce(self._mapper.usage_units_key, Value(units_fallback))
            sum_query = query.annotate(**sum_annotations).order_by()
            sum_units = {"cost_units": self.currency}
            if self._mapper.usage_units_key:
                sum_units["usage_units"] = (
                    sum_query.values("usage_units").first().get("usage_units", usage_units_fallback)
                )
            query_sum = self.calculate_total(**sum_units)
        else:
            sum_units["cost_units"] = self.currency
            if annotations.get("usage_units"):
                sum_units["usage_units"] = usage_units_fallback
            query_sum.update(sum_units)
            self._pack_data_object(query_sum, **self._mapper.PACK_DEFINITIONS)
        return query_sum

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
            query = query_table.objects.filter(self.query_filter)
            if self.query_exclusions:
                query = query.exclude(self.query_exclusions)
            query = query.annotate(**self.annotations)

            query_group_by = ["date"] + self._get_group_by()
            query_order_by = ["-date", self.order]

            annotations = self._mapper.report_type_map.get("annotations", {})
            query_data = query.values(*query_group_by).annotate(**annotations)

            if "account" in query_group_by:
                query_data = query_data.annotate(
                    account_alias=Coalesce(F(self._mapper.provider_map.get("alias")), "usage_account_id")
                )

            query_sum = self._build_sum(query, annotations)

            if self._limit and query_data and not org_unit_applied:
                query_data = self._group_by_ranks(query, query_data)
                if not self.parameters.get("order_by"):
                    # override implicit ordering when using ranked ordering.
                    query_order_by[-1] = "rank"

            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)

            query_data = self.order_by(query_data, query_order_by)

            # Fetch the data (returning list(dict))
            query_results = list(query_data)

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
        query = self.query_table.objects.filter(self.query_filter)
        if self.query_exclusions:
            query = query.exclude(self.query_exclusions)
        query = query.annotate(**self.annotations)

        aggregates = self._mapper.report_type_map.get("aggregates", {})

        total_query = query.aggregate(**aggregates)
        for unit_key, unit_value in units.items():
            total_query[unit_key] = unit_value

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

    def _get_sub_org_units(self, org_unit_list):
        """Get sub org units for a list of parent org units.
        Args:
            org_unit_list (list): list of parent org units
        Returns:
            sub_org_unit_list (list): list of sub org units
        """
        try:
            # Parent OU filters
            org_unit_objects = (
                AWSOrganizationalUnit.objects.filter(org_unit_id__in=org_unit_list)
                .filter(account_alias__isnull=True)
                .order_by("org_unit_id", "-created_timestamp")
                .distinct("org_unit_id")
            )

            # This is to remove the excluded values from the sub_org_units
            if "org_unit_id" in list(self.query_table_exclude_keys):
                org_unit_list.extend(org_id for org_id in self.parameters.get_exclude("org_unit_id", []))

            sub_org_unit_list = None
            if org_unit_objects:
                sub_org_units = []
                # Loop through parent ids to find children org units 1 level below.
                for org_unit_object in org_unit_objects:
                    sub_query = (
                        AWSOrganizationalUnit.objects.filter(level=(org_unit_object.level + 1))
                        .filter(org_unit_path__icontains=org_unit_object.org_unit_id)
                        .filter(account_alias__isnull=False)
                        .exclude(org_unit_id__in=org_unit_list)
                        .order_by("org_unit_id", "-created_timestamp")
                        .distinct("org_unit_id")
                    )
                    sub_org_units.append(sub_query)

                # only do a union if more than one org_unit_id was passed in.
                if len(sub_org_units) > 1:
                    sub_query_set = sub_org_units.pop()
                    sub_ou_ids_list = sub_query_set.union(*sub_org_units).values_list("org_unit_id", flat=True)
                    # Note: The django orm won't let you do an order_by & distinct on the union of
                    # multiple queries. The additional order_by &  distinct is essential to handle
                    # use cases like OU_005 being moved from OU_002 to OU_001.
                    sub_org_unit_list = (
                        AWSOrganizationalUnit.objects.filter(org_unit_id__in=sub_ou_ids_list)
                        .filter(account_alias__isnull=False)
                        .order_by("org_unit_id", "-created_timestamp")
                        .distinct("org_unit_id")
                    )
                else:
                    sub_org_unit_list = sub_org_units[0]
            return list(sub_org_unit_list) if sub_org_unit_list else []
        except Exception as e:
            LOG.error(f"Error getting sub org units: \n{e}")
            return []

    def format_ec2_response(self, query_data):
        """
        Format EC2 response data.

        If CSV output, nests query data under a date key.
        If not CSV output, tansforming tags in resource data to the desired UI format.

        Example transformation:

        Input:
        "tags": [
            {"Map":"c2"},
            {"Name":"instance_name_3"},
        ]


        Output:
        "tags": [
            {
                "key": "Map",
                "values": ["c2"]
            },
            {
                "key": "Name",
                "values": ["instance_name_3"]
            },
        ]

        Returns:
        list: The formatted query data based on the output format.
        """

        if not self.is_csv_output:
            for item in query_data:
                for resource in item["resource_ids"]:
                    resource_values = resource["values"][0]

                    seen_tags = set()
                    unique_tags = []

                    for tag in resource_values["tags"]:
                        if tag:
                            for key, value in tag.items():
                                tag_tuple = (key, tuple([value]))

                                if tag_tuple not in seen_tags:
                                    seen_tags.add(tag_tuple)
                                    unique_tags.append({"key": key, "values": [value]})

                    resource_values["tags"] = unique_tags

            return query_data

        else:
            date_string = self.date_to_string(self.time_interval[0])
            for item in query_data:
                # exclude tags when exporting to csv
                item.pop("tags")
            return [{"date": date_string, "resource_ids": query_data}]
