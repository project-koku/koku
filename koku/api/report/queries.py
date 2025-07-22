#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Query Handling for Reports."""
import copy
import logging
import random
import re
import string
from collections import defaultdict
from collections import OrderedDict
from decimal import Decimal
from decimal import DivisionByZero
from decimal import InvalidOperation
from functools import cached_property
from itertools import groupby
from json import dumps as json_dumps
from urllib.parse import quote
from urllib.parse import quote_from_bytes
from urllib.parse import unquote

import ciso8601
import numpy as np
import pandas as pd
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import Case
from django.db.models import CharField
from django.db.models import DecimalField
from django.db.models import F
from django.db.models import Q
from django.db.models import Value
from django.db.models import When
from django.db.models import Window
from django.db.models.expressions import OrderBy
from django.db.models.expressions import RawSQL
from django.db.models.functions import Coalesce
from django.db.models.functions import Concat
from django.db.models.functions import RowNumber
from pandas.api.types import CategoricalDtype

from api.currency.models import ExchangeRateDictionary
from api.models import Provider
from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.query_handler import QueryHandler
from api.report.constants import AWS_CATEGORY_PREFIX
from api.report.constants import TAG_PREFIX
from api.report.constants import URL_ENCODED_SAFE
from api.utils import safe_column_alias

LOG = logging.getLogger(__name__)


def strip_prefix(key, prefix):
    """Remove the query prefix from a key."""
    return key.replace(prefix, "").replace("and:", "").replace("or:", "")


def _is_grouped_by_key(group_by, keys):
    for key in keys:
        for k in group_by:
            if k.startswith(key):
                return True


def is_grouped_by_tag(parameters):
    """Determine if grouped by tag."""
    return _is_grouped_by_key(parameters.parameters.get("group_by", {}), ["tag"])


def is_grouped_by_project(parameters):
    """Determine if grouped or filtered by project."""
    return _is_grouped_by_key(parameters.parameters.get("group_by", {}), ["project", "and:project", "or:project"])


def is_grouped_by_node(parameters):
    """Determine if grouped by node."""
    return _is_grouped_by_key(parameters.parameters.get("group_by", {}), ["node", "and:node", "or:node"])


def check_if_valid_date_str(date_str):
    """Check to see if a valid date has been passed in."""
    try:
        ciso8601.parse_datetime(date_str)
    except (ValueError, TypeError):
        return False
    return True


def check_view_filter_and_group_by_criteria(filter_set, group_by_set):
    """Return a bool for whether a view can be used."""
    no_view_group_bys = {"project", "node"}
    # The dashboard does not show any data grouped by OpenShift cluster, node, or project
    # so we do not have views for these group bys
    if group_by_set.intersection(no_view_group_bys) or filter_set.intersection(no_view_group_bys):
        return False
    return True


def sanitize_tag(tag):
    """Sanitize a tag by removing unwanted characters and URL-encoding it."""
    characters_to_sanitize = r' "\'`;'
    table = str.maketrans(characters_to_sanitize, "_" * len(characters_to_sanitize))
    sanitized_tag = tag.translate(table)
    encoded_tag = str.encode(sanitized_tag)
    sanitized_tag = quote_from_bytes(encoded_tag, safe=URL_ENCODED_SAFE)
    return sanitized_tag


class ReportQueryHandler(QueryHandler):
    """Handles report queries and responses."""

    def __init__(self, parameters):
        """Establish report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        LOG.debug(f"Query Params: {parameters}")
        super().__init__(parameters)

        self._tag_keys = parameters.tag_keys
        self._aws_category = parameters.aws_category_keys
        self._category = parameters.category
        if not hasattr(self, "_report_type"):
            self._report_type = parameters.report_type
        replace_delta = {"cost": "cost_total"}
        self._delta = replace_delta.get(parameters.delta, parameters.delta)
        self._offset = parameters.get_filter("offset", default=0)
        self.query_delta = {"value": None, "percent": None}
        self.query_exclusions = None

        self.query_filter = self._get_filter()  # sets self.query_exclusions
        LOG.debug(f"query_exclusions: {self.query_exclusions}")

        self.is_csv_output = self.parameters.accept_type and "text/csv" in self.parameters.accept_type

    @cached_property
    def query_table_access_keys(self):
        """Return the access keys specific for selecting the query table."""
        return set(self.parameters.get("access", {}).keys())

    @cached_property
    def query_table_group_by_keys(self):
        """Return the group by keys specific for selecting the query table."""
        return set(self.parameters.get("group_by", {}).keys())

    @cached_property
    def query_table_filter_keys(self):
        """Return the filter keys specific for selecting the query table."""
        excluded_filters = {"time_scope_value", "time_scope_units", "resolution", "limit", "offset"}
        filter_keys = set(self.parameters.get("filter", {}).keys())
        return filter_keys.difference(excluded_filters)

    @cached_property
    def query_table_exclude_keys(self):
        """Return the exclude keys specific for selecting the query table."""
        return set(self.parameters.get("exclude", {}).keys())

    @property
    def report_annotations(self):
        """Return annotations with the correct capacity field."""
        return self._mapper.report_type_map.get("annotations", {})

    @cached_property
    def query_table(self):
        """Return the database table or view to query against."""
        query_table = self._mapper.query_table
        report_type = self._report_type
        report_group = "default"

        if self.provider in (
            Provider.OCP_AWS,
            Provider.OCP_AZURE,
            Provider.OCP_ALL,
        ) and not check_view_filter_and_group_by_criteria(
            self.query_table_filter_keys, self.query_table_group_by_keys
        ):
            return query_table

        key_tuple = tuple(
            sorted(
                self.query_table_filter_keys.union(
                    self.query_table_group_by_keys, self.query_table_access_keys, self.query_table_exclude_keys
                )
            )
        )
        if key_tuple:
            report_group = key_tuple

        # Special Casess for Network and Database Cards in the UI
        service_filter = set(self.parameters.get("filter", {}).get("service", []))
        if self.provider in (Provider.PROVIDER_AZURE, Provider.OCP_AZURE):
            service_filter = set(self.parameters.get("filter", {}).get("service_name", []))
        if report_type == "costs" and service_filter and not service_filter.difference(self.network_services):
            report_type = "network"
        elif report_type == "costs" and service_filter and not service_filter.difference(self.database_services):
            report_type = "database"

        try:
            query_table = self._mapper.views[report_type][report_group]
        except KeyError:
            msg = f"{report_group} for {report_type} has no entry in views. Using the default."
            LOG.warning(msg)
        return query_table

    @property
    def is_openshift(self):
        """Determine if we are working with an OpenShift API."""
        return "openshift" in self.parameters.request.path

    @property
    def is_aws(self):
        """Determine if we are working with an AWS API."""
        return "aws" in self.parameters.request.path

    def initialize_totals(self):
        """Initialize the total response column values."""
        query_sum = {}
        for value in self._mapper.report_type_map.get("aggregates").keys():
            query_sum[value] = 0
        return query_sum

    def get_tag_filter_keys(self, parameter_key="filter"):
        """Get tag keys from filter arguments."""
        tag_filters = []
        filters = self.parameters.get(parameter_key, {})
        for filt in filters:
            if "tag" in filt and filt in self._tag_keys:
                tag_filters.append(filt)
        return tag_filters

    def get_aws_category_keys(self, parameter_key="filter"):
        """Get aws_category keys from filter arguments."""
        aws_category_parameters = []
        parameters = self.parameters.get(parameter_key, {})
        for filt in parameters:
            if AWS_CATEGORY_PREFIX.replace(":", "") in filt and filt in self._aws_category:
                aws_category_parameters.append(filt)
        return aws_category_parameters

    def get_tag_group_by_keys(self):
        """Get tag keys from group by arguments."""
        tag_groups = []
        filters = self.parameters.get("group_by", {})
        for filt in filters:
            if "tag" in filt and filt in self._tag_keys:
                tag_groups.append(filt)
        return tag_groups

    def _build_custom_filter_list(self, filter_type, method, filter_list):
        """Replace filter list items from custom method."""
        if filter_type == "infrastructures" and method:
            for item in filter_list:
                custom_list = method(item, self.tenant)
                if not custom_list:
                    random_name = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
                    custom_list = [random_name]
                filter_list.remove(item)
                filter_list = list(set(filter_list + custom_list))
        return filter_list

    def _check_for_operator_specific_filters(self, filter_collection):
        """Checks for operator specific fitlers, and adds them to the filter collection

        Notes:
            Tag exclusions are constructed to use Django's `.filter` instead of
            `.exclude`. Django adds "IS NOT NULL" when using `.exclude` which removes
            the `no-{option}` results.
        """
        # Tag prefixed filters
        tag_filters = self.get_tag_filter_keys()
        tag_group_by = self.get_tag_group_by_keys()
        tag_filters.extend(tag_group_by)
        filter_collection = self._set_prefix_based_filters(
            filter_collection, self._mapper.tag_column, tag_filters, TAG_PREFIX
        )
        tag_exclude_filters = self.get_tag_filter_keys("exclude")
        tag_exclusion_composed = self._set_prefix_based_exclusions(
            self._mapper.tag_column, tag_exclude_filters, TAG_PREFIX
        )
        # aws_category prefixed filters
        aws_category_exclusion_composed = None
        if aws_category_column := self._mapper.provider_map.get("aws_category_column"):
            aws_category_filters = self.get_aws_category_keys("filter")
            aws_category_group_by = self.get_aws_category_keys("group_by")
            aws_category_filters.extend(aws_category_group_by)
            filter_collection = self._set_prefix_based_filters(
                filter_collection, aws_category_column, aws_category_filters, AWS_CATEGORY_PREFIX
            )
            aws_category_exclude_filters = self.get_aws_category_keys("exclude")
            aws_category_exclusion_composed = self._set_prefix_based_exclusions(
                aws_category_column, aws_category_exclude_filters, AWS_CATEGORY_PREFIX
            )

        composed_filters = filter_collection.compose()
        and_composed_filters = self._set_operator_specified_filters("and")
        or_composed_filters = self._set_operator_specified_filters("or")
        exact_composed_filters = self._set_operator_specified_filters("exact")
        composed_filters = composed_filters & and_composed_filters & or_composed_filters & exact_composed_filters
        if tag_exclusion_composed:
            composed_filters = composed_filters & tag_exclusion_composed
        if aws_category_exclusion_composed:
            composed_filters = composed_filters & aws_category_exclusion_composed
        return composed_filters

    def _check_for_operator_specific_exclusions(self, composed_filters):
        """Check for operator specific filters for exclusions."""
        # Tag exclusion filters are added to the self.query_filter. COST-3199
        and_composed_filters = self._set_operator_specified_filters("and", True)
        or_composed_filters = self._set_operator_specified_filters("or", True)
        exact_composed_filters = self._set_operator_specified_filters("exact", True)
        if composed_filters:
            composed_filters = composed_filters & and_composed_filters & or_composed_filters & exact_composed_filters
        else:
            composed_filters = and_composed_filters & or_composed_filters & exact_composed_filters
        return composed_filters

    def _get_search_filter(self, filters):  # noqa C901
        """Populate the query filter collection for search filters.

        Args:
            filters (QueryFilterCollection): collection of query filters
        Returns:
            (QueryFilterCollection): populated collection of query filters

        """
        # define filter parameters using API query params.
        fields = self._mapper._provider_map.get("filters")

        access_filters = QueryFilterCollection()

        aws_use_or_operator = self.parameters.parameters.get("aws_use_or_operator", False)
        if aws_use_or_operator:
            aws_or_filter_collections = filters.compose()
            filters = QueryFilterCollection()

        if self._category:
            category_filters = QueryFilterCollection()
        exclusion = QueryFilterCollection()
        composed_category_filters = None
        composed_exclusions = None

        for q_param, filt in fields.items():
            access = self.parameters.get_access(q_param, list())
            group_by = self.parameters.get_group_by(q_param, list())
            exclude_ = self.parameters.get_exclude(q_param, list())
            filter_ = self.parameters.get_filter(q_param, list())
            list_ = list(set(group_by + filter_))  # uniquify the list
            if isinstance(filt, list):
                for _filt in filt:
                    if not ReportQueryHandler.has_wildcard(list_):
                        for item in list_:
                            q_filter = QueryFilter(parameter=item, **_filt)
                            filters.add(q_filter)
                    for item in exclude_:
                        exclude_filter = QueryFilter(parameter=item, **_filt)
                        exclusion.add(exclude_filter)
            else:
                list_ = self._build_custom_filter_list(q_param, filt.get("custom"), list_)
                if not ReportQueryHandler.has_wildcard(list_):
                    for item in list_:
                        if self._category:
                            if any([item in cat for cat in self._category]):
                                q_cat_filter = QueryFilter(
                                    parameter=item, **{"field": "cost_category__name", "operation": "icontains"}
                                )
                                category_filters.add(q_cat_filter)
                                q_filter = QueryFilter(parameter=item, **filt)
                                category_filters.add(q_filter)
                            else:
                                q_filter = QueryFilter(parameter=item, **filt)
                                category_filters.add(q_filter)
                            composed_category_filters = category_filters.compose(logical_operator="or")
                        else:
                            q_filter = QueryFilter(parameter=item, **filt)
                            filters.add(q_filter)
                exclude_ = self._build_custom_filter_list(q_param, filt.get("custom"), exclude_)
                for item in exclude_:
                    if self._category:
                        if any([item in cat for cat in self._category]):
                            exclude_cat_filter = QueryFilter(
                                parameter=item, **{"field": "cost_category__name", "operation": "icontains"}
                            )
                            exclusion.add(exclude_cat_filter)
                    exclude_filter = QueryFilter(parameter=item, **filt)
                    exclusion.add(exclude_filter)
            if access:
                access_filt = copy.deepcopy(filt)
                self.set_access_filters(access, access_filt, access_filters)
        composed_exclusions = exclusion.compose(logical_operator="or")
        self.query_exclusions = self._check_for_operator_specific_exclusions(composed_exclusions)
        provider_map_exclusions = self._provider_map_conditional_exclusions()
        if provider_map_exclusions:
            self.query_exclusions = self.query_exclusions | provider_map_exclusions
        composed_filters = self._check_for_operator_specific_filters(filters)
        if composed_category_filters:
            composed_filters = composed_filters & composed_category_filters
        # Additional filter[] specific options to consider.
        multi_field_or_composed_filters = self._set_or_filters()
        if aws_use_or_operator and aws_or_filter_collections:
            composed_filters = aws_or_filter_collections & composed_filters
        if access_filters:
            if aws_use_or_operator:
                composed_access_filters = access_filters.compose(logical_operator="or")
                composed_filters = aws_or_filter_collections & composed_access_filters
            else:
                composed_access_filters = access_filters.compose()
                composed_filters = composed_filters & composed_access_filters
        if multi_field_or_composed_filters:
            composed_filters = composed_filters & multi_field_or_composed_filters
        LOG.debug(f"_get_search_filter: {composed_filters}")
        LOG.debug(f"self.query_exclusions: {self.query_exclusions}")
        return composed_filters

    def _provider_map_conditional_exclusions(self):
        """
        Uses the provider_map conditionals to exclude from a query in certain scenarios.

        Such as when we fall back to the daily summary table but don't want Unallocated projects
        included for OCP compute/memory endpoints.
        """

        exclusions = QueryFilterCollection()
        exclude_list = (
            self._mapper.report_type_map.get("conditionals", {}).get(self.query_table, {}).get("exclude", [])
        )
        for exclusion in exclude_list:
            exclusions.add(**exclusion)
        return exclusions.compose()

    def _set_or_filters(self, or_filter=None):
        """Create a composed filter collection of ORed filters.

        This is designed to handle specific cases in the provider_map
        not to accomodate user input via the API.

        """
        filters = QueryFilterCollection()
        if not or_filter:
            or_filter = self._mapper._report_type_map.get("or_filter", [])
        for filt in or_filter:
            q_filter = QueryFilter(**filt)
            filters.add(q_filter)

        return filters.compose(logical_operator="or")

    def _set_prefix_based_exclusions(self, db_column, exclude_filters, prefix):
        """Creates exclusion fitlers for prefixed parameter keys
        that allow null returns.

        db_column: column to apply the excludes on
        exclude_filters: list of exclude filters
        prefix: prefix to be stripped from parameter keys

        Notes:
        Null filters are added to create the no-{key} in the api return.
        They are added as a separate QueryFilterCollection because we need
        the nulls to be AND together in order to handle different tag
        key values.

        noticontainslist is a custom django lookup we wrote to handle
        prefixed exclusions.
        """
        null_collections = QueryFilterCollection()
        _filter_list = []
        empty_json_filter = {"field": db_column, "operation": "exact", "parameter": "{}"}
        for exclude_key in exclude_filters:
            exclude_db_name = db_column + "__" + strip_prefix(exclude_key, prefix)
            list_ = self.parameters.get_exclude(exclude_key, list())
            if list_ and not ReportQueryHandler.has_wildcard(list_):
                _filter_list.append({"field": exclude_db_name, "operation": "noticontainslist", "parameter": list_})
                null_collections.add(
                    QueryFilter(**{"field": exclude_db_name, "operation": "isnull", "parameter": True})
                )
        null_composed = null_collections.compose()
        if self.provider and self.provider in [
            Provider.OCP_AWS,
            Provider.OCP_AZURE,
            Provider.OCP_ALL,
            Provider.OCP_GCP,
            Provider.PROVIDER_OCP,
        ]:
            # For OCP tables we need to use the AND operator because the two prefixed keys are
            # found in the same json structure per row.
            _exclusion_composed = None
            for _filt in _filter_list:
                _filt_composed = QueryFilterCollection([QueryFilter(**_filt)]).compose()
                if not _exclusion_composed:
                    _exclusion_composed = _filt_composed
                else:
                    if self._report_type == "virtual_machines":
                        _exclusion_composed = _exclusion_composed | _filt_composed
                    else:
                        _exclusion_composed = _exclusion_composed & _filt_composed
            if _exclusion_composed:
                _exclusion_composed = (
                    _exclusion_composed | QueryFilterCollection([QueryFilter(**empty_json_filter)]).compose()
                )
        else:
            if _filter_list:
                _filter_list.append(empty_json_filter)
            # We use OR here for our non ocp tables because the  keys will not live in the
            # same json structure.
            _exclusion_composed = self._set_or_filters(_filter_list)
        if _exclusion_composed and null_composed:
            _exclusion_composed = _exclusion_composed | null_composed
        return _exclusion_composed

    def _set_operator_specific_prefix_based_filters(self, filter_collection, db_column, filter_list, operator, prefix):
        """Create operator specific prefix based filters.

        filter_collection: FilterCollection
        db_column: column to use to build filter
        filter_list: list of filters from param's filter & group by
        operator: operator to combine filters on
        prefix: prefix to be stripped from parameter keys
        """
        operator_filters = [filt for filt in filter_list if operator + ":" in filt]
        for _filter in operator_filters:
            # Update the _filter to use the label column name
            _db_name = db_column + "__" + strip_prefix(_filter, prefix)
            filt = {"field": _db_name, "operation": "icontains"}
            group_by = self.parameters.get_group_by(_filter, list())
            filter_ = self.parameters.get_filter(_filter, list())
            list_ = list(set(group_by + filter_))  # uniquify the list
            if list_ and not ReportQueryHandler.has_wildcard(list_):
                for item in list_:
                    q_filter = QueryFilter(parameter=item, logical_operator=operator, **filt)
                    filter_collection.add(q_filter)
        return filter_collection

    def _set_prefix_based_filters(self, filter_collection, db_column, filter_list, prefix):
        """Create and set colon prefixed filters.

        filter_collection: FilterCollection
        db_column: column to use to build filter
        filter_list: list of filters from param's filter & group by
        prefix: prefix to be stripped from parameter keys
        """
        standard_filters = [filt for filt in filter_list if "and:" not in filt and "or:" not in filt]
        for prefix_filter in standard_filters:
            # Update the _filter to use the label column name
            db_name = db_column + "__" + strip_prefix(prefix_filter, prefix)
            filt = {"field": db_name, "operation": "icontains"}
            group_by = self.parameters.get_group_by(prefix_filter, list())
            filter_ = self.parameters.get_filter(prefix_filter, list())
            list_ = list(set(group_by + filter_))  # uniquify the list
            if filter_ and ReportQueryHandler.has_wildcard(filter_):
                filt = {"field": db_column, "operation": "has_key"}
                q_filter = QueryFilter(parameter=strip_prefix(prefix_filter, prefix), **filt)
                filter_collection.add(q_filter)
            elif list_ and not ReportQueryHandler.has_wildcard(list_):
                for item in list_:
                    q_filter = QueryFilter(parameter=item, **filt)
                    filter_collection.add(q_filter)

        filter_collection = self._set_operator_specific_prefix_based_filters(
            filter_collection, db_column, filter_list, "and", prefix
        )
        filter_collection = self._set_operator_specific_prefix_based_filters(
            filter_collection, db_column, filter_list, "or", prefix
        )

        return filter_collection

    def _set_operator_specified_filters(self, operator, check_for_exclude=False):
        """Set any filters using AND instead of OR."""
        fields = self._mapper._provider_map.get("filters")
        filters = QueryFilterCollection()
        composed_filter = Q()

        for q_param, filt in fields.items():
            q_param = operator + ":" + q_param
            group_by = self.parameters.get_group_by(q_param, list())
            if check_for_exclude:
                list_ = self.parameters.get_exclude(q_param, list())
            else:
                filter_ = self.parameters.get_filter(q_param, list())
                list_ = list(set(group_by + filter_))  # uniquify the list
            logical_operator = operator
            # This is a flexibilty feature allowing a user to set
            # a single and: value and still get a result instead
            # of erroring on validation
            if len(list_) < 2 and logical_operator != "exact":
                logical_operator = "or"
            if list_ and not ReportQueryHandler.has_wildcard(list_):
                if isinstance(filt, list):
                    for _filt in filt:
                        filt_filters = QueryFilterCollection()
                        for item in list_:
                            q_filter = QueryFilter(parameter=item, logical_operator=logical_operator, **_filt)
                            filt_filters.add(q_filter)
                        # List filter are a complex mix of and/or logic
                        # Each filter in the list must be ORed together
                        # regardless of the operator on the item in the filter
                        # Ex:
                        # (OR:
                        #     (AND:
                        #         ('cluster_alias__icontains', 'ni'),
                        #         ('cluster_alias__icontains', 'se')
                        #     ),
                        #     (AND:
                        #         ('cluster_id__icontains', 'ni'),
                        #         ('cluster_id__icontains', 'se')
                        #     )
                        # )
                        composed_filter = composed_filter | filt_filters.compose()
                else:
                    list_ = self._build_custom_filter_list(q_param, filt.get("custom"), list_)
                    for item in list_:
                        q_filter = QueryFilter(parameter=item, logical_operator=logical_operator, **filt)
                        filters.add(q_filter)
        if filters:
            composed_filter = composed_filter & filters.compose()
        return composed_filter

    def _get_filter(self, delta=False):
        """Create dictionary for filter parameters.

        Args:
            delta (Boolean): Construct timeframe for delta
        Returns:
            (Dict): query filter dictionary

        """
        if "gcp_filters" in dir(self._mapper) and self._mapper.gcp_filters:
            filters = super()._get_gcp_filter(delta)
        else:
            filters = super()._get_filter(delta)

        # set up filters for instance-type and storage queries.
        for filter_map in self._mapper._report_type_map.get("filter"):
            filters.add(**filter_map)

        # define filter parameters using API query params.
        composed_filters = self._get_search_filter(filters)

        LOG.debug(f"_get_filter: {composed_filters}")
        return composed_filters

    def _get_group_by(self):
        """Create list for group_by parameters."""
        group_by = []
        for item in self.group_by_options:
            group_data = self.parameters.get_group_by(item)
            if not group_data:
                group_data = self.parameters.get_group_by("and:" + item)
            if not group_data:
                group_data = self.parameters.get_group_by("or:" + item)
            if group_data:
                group_pos = None
                try:
                    group_pos = self.parameters.url_data.index(item)
                except ValueError:
                    # if we are grouping by org unit we are inserting a group by account
                    # and popping off the org_unit_id group by - but here we need to get the position
                    # for org_unit_id
                    if item == "account" and "org_unit_id" in self.parameters.url_data:
                        group_pos = self.parameters.url_data.index("org_unit_id")
                if (item, group_pos) not in group_by:
                    group_by.append((item, group_pos))

        tag_group_by = self._get_tag_group_by()
        group_by.extend(tag_group_by)
        group_by.extend(self._get_aws_category_group_by())
        group_by = sorted(group_by, key=lambda g_item: g_item[1])
        group_by = [item[0] for item in group_by]

        # This is a current workaround for AWS instance-types reports
        # It is implied that limiting is performed by account/region and
        # not by instance type when those group by params are used.
        # For that ranking to work we can't also group by instance_type.
        inherent_group_by = self._mapper._report_type_map.get("group_by")
        if inherent_group_by and not (group_by and self._limit):
            group_by = group_by + list(set(inherent_group_by) - set(group_by))

        return group_by

    def _get_tag_group_by(self):
        """Create list of tag-based group by parameters."""
        group_by = []
        tag_groups = self.get_tag_group_by_keys()
        for tag in tag_groups:
            raw_key = strip_prefix(tag, TAG_PREFIX)
            decoded_key = unquote(raw_key)
            safe_key = safe_column_alias(decoded_key)
            tag_db_name = f"{self._mapper.tag_column}__{safe_key}"

            # Try to find the position of the tag in the original URL parameters
            group_pos = None
            for idx, param in enumerate(self.parameters.url_data):
                if unquote(param) == tag:
                    group_pos = idx
                    break
            # If the tag is not found, skip this group_by entry
            if group_pos is None:
                LOG.warning(f"Could not resolve tag position for: {tag}")
                continue

            group_by.append((tag_db_name, group_pos))
        return group_by

    def _get_aws_category_group_by(self):
        """Return list of aws_category based group by parameters."""
        group_by = []
        if aws_category_column := self._mapper.provider_map.get("aws_category_column"):
            groups = self.get_aws_category_keys("group_by")
            for aws_category in groups:
                raw_key = strip_prefix(aws_category, AWS_CATEGORY_PREFIX)
                decoded_key = unquote(raw_key)
                safe_key = safe_column_alias(decoded_key)
                db_name = f"{aws_category_column}__{safe_key}"
                encoded_url_key = quote(decoded_key, safe=URL_ENCODED_SAFE)
                group_pos = self.parameters.url_data.index(encoded_url_key)
                group_by.append((db_name, group_pos))
        return group_by

    @cached_property
    def exchange_rates(self):
        try:
            return ExchangeRateDictionary.objects.first().currency_exchange_dictionary
        except AttributeError as err:
            LOG.warning(f"Exchange rates dictionary is not populated resulting in {err}.")
            return {}

    @cached_property
    def exchange_rate_annotation_dict(self):
        """Get the exchange rate annotation based on the exchange_rates property."""
        whens = [
            When(**{self._mapper.cost_units_key: k, "then": Value(v.get(self.currency))})
            for k, v in self.exchange_rates.items()
        ]
        return {"exchange_rate": Case(*whens, default=1, output_field=DecimalField())}

    def _project_classification_annotation(self, query_data):
        """Get the correct annotation for a project or category"""
        whens = [
            When(project__startswith="openshift-", then=Value("default")),
            When(project__startswith="kube-", then=Value("default")),
            When(project="openshift", then=Value("default")),
            When(project__in=["Platform unallocated", "Worker unallocated"], then=Value("unallocated")),
            When(project__in=["Storage unattributed", "Network unattributed"], then=Value("unattributed")),
        ]

        if self._category:
            whens.append(When(project__in=self._category, then=Concat(Value("category_"), F("cost_category__name"))))

        return query_data.annotate(
            classification=Case(
                *whens,
                default=Value("project"),
                output_field=CharField(),
            )
        )

    @property
    def annotations(self):
        """Create dictionary for query annotations.

        Args:
            fields (dict): Fields to create annotations for

        Returns:
            (Dict): query annotations dictionary

        """
        raise NotImplementedError("Annotations must be defined by sub-classes.")

    @staticmethod
    def _group_data_by_list(group_by_list, group_index, data):
        """Group data by list.

        Args:
            group_by_list (List): list of strings to group data by
            group_index (Int): Position in group_by_list that contains group to group by
            data    (List): list of query results
        Returns:
            (Dict): dictionary of grouped query results or the original data

        """
        group_by_list_len = len(group_by_list)
        if group_index >= group_by_list_len:
            return data

        out_data = OrderedDict()
        curr_group = group_by_list[group_index]

        # FIXME: data needs to be sorted before passing to groupby because
        #        groupby aggregates new groups every time it hits a new item while
        #        iterating with no regard for what groups already exist.
        for key, group in groupby(data, lambda by: by.get(curr_group)):
            grouped = list(group)
            grouped = ReportQueryHandler._group_data_by_list(group_by_list, (group_index + 1), grouped)

            # Default to empty list for use in the set() constructor later on
            if datapoint := out_data.get(key, []):
                try:
                    # If datapoint is a list, combine it with grouped
                    out_data[key] = grouped + datapoint
                except TypeError:
                    # datapoint is a dictionary
                    #
                    # Update the data if any keys in the grouped dictionary exist in the datapoint.
                    for inter_key in set(datapoint).intersection(grouped):
                        data_to_update = grouped[inter_key]
                        try:
                            data_to_update.update(datapoint[inter_key])
                        except AttributeError:
                            # data_to_update is a list of dicts
                            data_to_update.extend(datapoint[inter_key])

                    out_data[key].update(grouped)
            else:
                out_data[key] = grouped

        return out_data

    def _clean_prefix_grouping_labels(self, group, all_pack_keys=[]):
        """build grouping prefix"""
        check_pack_prefix = None
        prefix_mapping = {TAG_PREFIX: self._mapper.tag_column}
        if aws_category_column := self._mapper.provider_map.get("aws_category_column"):
            prefix_mapping[AWS_CATEGORY_PREFIX] = aws_category_column
        for prefix, db_column in prefix_mapping.items():
            if group.startswith(db_column + "__"):
                group = group[len(db_column + "__") :]  # noqa
                check_pack_prefix = prefix
        if check_pack_prefix and group in all_pack_keys:
            group = check_pack_prefix + group
        return group

    def _apply_group_null_label(self, data, groupby=None):
        """Apply any no-{group} labels needed before grouping data.

        Args:
            data (Dict): A row of the queried data
            group_by (list): An optional list of groups
        Returns:
            (Dict): Data updated with no-group labels

        """
        if groupby is None:
            return data

        for group in groupby:
            if group in data and pd.isnull(data.get(group)) or data.get(group) == "":
                value = self._clean_prefix_grouping_labels(group)
                group_label = f"No-{value}"
                data[group] = group_label

        return data

    def _apply_group_by(self, query_data, group_by=None):
        """Group data by date for given time interval then group by list.

        Args:
            query_data  (List(Dict)): Queried data
            group_by (list): An optional list of groups
        Returns:
            (Dict): Dictionary of grouped dictionaries

        """
        bucket_by_date = OrderedDict()

        if group_by is None:
            group_by = self._get_group_by()

        for item in self.time_interval:
            date_string = self.date_to_string(item)
            bucket_by_date[date_string] = []

        for result in query_data:
            if self._limit and result.get("rank"):
                del result["rank"]
            self._apply_group_null_label(result, group_by)
            date_string = result.get("date")
            date_bucket = bucket_by_date.get(date_string)
            if date_bucket is not None:
                date_bucket.append(result)

        for date, data_list in bucket_by_date.items():
            grouped = ReportQueryHandler._group_data_by_list(group_by, 0, data_list)
            bucket_by_date[date] = grouped
        return bucket_by_date

    def _initialize_response_output(self, parameters):
        """Initialize output response object."""
        output = copy.deepcopy(parameters.parameters)
        # remove access from the output
        output.pop("access")

        return output

    def _pack_data_object(self, data, **kwargs):  # noqa: C901
        """Pack data into object format."""
        if not isinstance(data, dict):
            return data

        all_pack_keys = ["date", "delta_value", "delta_percent"]
        kwargs_values = kwargs.values()
        for pack_def in kwargs_values:
            remove_keys = []
            key_items = pack_def.get("keys")
            key_units = pack_def.get("units")
            if isinstance(key_items, dict):
                for data_key, group_info in key_items.items():
                    units = data.get(key_units)
                    value = data.get(data_key)
                    if value is not None:
                        group_key = group_info.get("group")
                        new_key = group_info.get("key")
                        if data.get(group_key):
                            if isinstance(data[group_key], str):
                                # This if is to overwrite the "cost": "No-cost"
                                # that is provided by the order_by function.
                                data[group_key] = {}
                        else:
                            data[group_key] = {}
                        if units:
                            data[group_key][new_key] = {"value": value, "units": units}
                        else:
                            data[group_key][new_key] = value
                        remove_keys.append(data_key)
            else:
                if key_items:
                    all_pack_keys += key_items
                for key in key_items:
                    units = data.get(key_units)
                    value = data.get(key)
                    if value is not None and units is not None:
                        data[key] = {"value": value, "units": units}
            if units is not None:
                del data[key_units]
            for key in remove_keys:
                if key in data:
                    del data[key]
        delete_keys = []
        new_data = {}
        for data_key in data.keys():
            clean_prefix = self._clean_prefix_grouping_labels(data_key, all_pack_keys)
            if clean_prefix != data_key:
                new_data[clean_prefix] = data[data_key]
                delete_keys.append(data_key)
        for del_key in delete_keys:
            if data.get(del_key):
                del data[del_key]
        data.update(new_data)
        return data

    def _transform_data(self, groups, group_index, data):
        """Transform dictionary data points to lists."""
        groups_len = len(groups)
        if not groups or group_index >= groups_len:
            pack = self._mapper.PACK_DEFINITIONS
            for item in data:
                self._pack_data_object(item, **pack)
            return data

        out_data = []
        label = "values"
        group_type = groups[group_index]
        next_group_index = group_index + 1

        if next_group_index < groups_len:
            label = groups[next_group_index] + "s"
            label = self._clean_prefix_grouping_labels(label)

        for group, group_value in data.items():
            group_title = self._clean_prefix_grouping_labels(group_type)
            group_label = group
            if group is None:
                group_label = f"No-{group_title}"
            cur = {group_title: group_label, label: self._transform_data(groups, next_group_index, group_value)}
            out_data.append(cur)

        return out_data

    def order_by(self, query_data, query_order_by):
        """Order a list of dictionaries by dictionary keys.

        Args:
            data (list): Query data that has been converted from QuerySet to list.
            order_fields (list): The list of dictionary keys to order by.

        Returns
            (list): The sorted/ordered list

        """
        if not query_data:
            return query_data
        if not (order_date := self.parameters.get("cost_explorer_order_by", {}).get("date")):
            return self._order_by(query_data, query_order_by)
        filtered_query_data = filter(lambda x: x["date"] == order_date, query_data)
        ordered_data = self._order_by(filtered_query_data, query_order_by)
        if not ordered_data:
            return self._order_by(query_data, query_order_by)
        df = pd.DataFrame(query_data)
        sort_terms = self._get_group_by()
        none_sort_terms = [f"No-{sort_term}" for sort_term in sort_terms]
        for sort_term, none_sort_term in zip(sort_terms, none_sort_terms):
            # use a dictionary to uniquify the list and maintain the correct order
            ordered_list = dict.fromkeys([entry.get(sort_term) or none_sort_term for entry in ordered_data]).keys()
            df[sort_term] = df[sort_term].fillna(none_sort_term).astype(CategoricalDtype(ordered_list, ordered=True))
        bys = list(reversed(sort_terms + ["date"]))
        df = df.sort_values(by=bys)
        for sort_term, none_sort_term in zip(sort_terms, none_sort_terms):
            df[sort_term] = df[sort_term].replace({none_sort_term: None})
        return df.to_dict("records")

    def _order_by(self, data, order_fields):
        """Order a list of dictionaries by dictionary keys.

        Args:
            data (list): Query data that has been converted from QuerySet to list.
            order_fields (list): The list of dictionary keys to order by.

        Returns
            (list): The sorted/ordered list

        """
        numeric_ordering = [
            "date",
            "rank",
            "delta",
            "delta_percent",
            "total",
            "usage",
            "request",
            "limit",
            "sup_total",
            "infra_total",
            "cost_total",
            "cost_total_distributed",
            "storage_class",
            "request_cpu",
            "request_memory",
        ]
        db_tag_prefix = self._mapper.tag_column + "__"
        sorted_data = data

        for field in reversed(order_fields):
            reverse = False
            field = field.replace("delta", "delta_percent")
            if field.startswith("-"):
                reverse = True
                field = field[1:]
            if field in numeric_ordering:
                sorted_data = sorted(
                    sorted_data, key=lambda entry: (entry.get(field) is None, entry.get(field)), reverse=reverse
                )
            elif TAG_PREFIX in field:
                tag_index = field.index(TAG_PREFIX) + len(TAG_PREFIX)
                tag = db_tag_prefix + field[tag_index:]
                sanitized_tag = sanitize_tag(tag)
                sorted_data = sorted(
                    sorted_data,
                    key=lambda entry: (entry.get(sanitized_tag) is None, entry.get(sanitized_tag)),
                    reverse=reverse,
                )
            else:
                for line_data in sorted_data:
                    if not line_data.get(field):
                        line_data[field] = f"No-{field}"
                sorted_data = sorted(
                    sorted_data,
                    key=lambda entry: (bool(re.match(r"other*", entry[field].lower())), entry[field].lower()),
                    reverse=reverse,
                )

        return sorted_data

    def get_tag_order_by(self, tag):
        """Generate an OrderBy clause forcing JSON column->key to be used.

        This is only for helping to create a Window() for purposes of grouping
        by tag.

        Args:
            tag (str): The Django formatted tag string
                       Ex. pod_labels__key

        Returns:
            OrderBy: A Django OrderBy clause using raw SQL

        """
        descending = True if self.order_direction == "desc" else False
        tag_column, tag_value = tag.split("__")
        sanitized_tag_value = sanitize_tag(tag_value)
        return OrderBy(RawSQL(f"{tag_column} -> %s", (sanitized_tag_value,)), descending=descending)

    def _percent_delta(self, a, b):
        """Calculate a percent delta.

        Args:
            a (int or float or Decimal) the current value
            b (int or float or Decimal) the previous value

        Returns:
            (Decimal) (a - b) / b * 100

            Returns Decimal(0) if b is zero or rounds to 0.00.

        """
        if round(b, 2) == 0:
            return None
        try:
            return Decimal((a - b) / b * 100)
        except (DivisionByZero, ZeroDivisionError, InvalidOperation):
            return None

    def _group_by_ranks(self, query, data):  # noqa: C901
        """Handle grouping data by filter limit."""
        group_by_value = self._get_group_by()
        gb = group_by_value if group_by_value else ["date"]
        tag_column = self._mapper.tag_column
        rank_orders = []

        rank_annotations = {}
        if ("delta" in self.order) or ("-delta" in self.order):
            if "__" in self._delta:
                a, b = self._delta.split("__")
                rank_annotations = {a: self.report_annotations[a], b: self.report_annotations[b]}
                rank_orders.append(getattr(F(a) / F(b), self.order_direction)())
            else:
                rank_annotations = {self._delta: self.report_annotations[self._delta]}
                rank_orders.append(getattr(F(self._delta), self.order_direction)())
        elif self._limit and "offset" in self.parameters.get("filter", {}) and self.parameters.get("order_by"):
            if self.report_annotations.get(self.order_field):
                rank_annotations = {self.order_field: self.report_annotations.get(self.order_field)}
            # AWS is special and account alias is a foreign key field so special_rank was annotated on the query
            if self.order_field == "account_alias":
                rank_orders.append(getattr(F("special_rank"), self.order_direction)())
            else:
                rank_orders.append(getattr(F(self.order_field), self.order_direction)())
        else:
            if self.order_field not in self.report_annotations.keys():
                for key, val in self.default_ordering.items():
                    order_field, order_direction = key, val
                rank_annotations = {order_field: self.report_annotations.get(order_field)}
                rank_orders.append(getattr(F(order_field), order_direction)())
            else:
                rank_annotations = {
                    self.order_field: self.report_annotations.get(self.order_field, self.order_direction)
                }
                rank_orders.append(getattr(F(self.order_field), self.order_direction)())

        if tag_column in gb[0]:
            rank_orders.append(self.get_tag_order_by(gb[0]))

        if self.order_field == "subscription_name":
            group_by_value.append("subscription_name")

        ranks = (
            query.annotate(**self.annotations)
            .values(*group_by_value)
            .annotate(**rank_annotations)
            .annotate(source_uuid=ArrayAgg(F("source_uuid"), filter=Q(source_uuid__isnull=False), distinct=True))
        )
        if self.is_aws and "account" in self._get_group_by():
            ranks = ranks.annotate(**{"account_alias": F("account_alias__account_alias")})
        if self.is_openshift:
            ranks = ranks.annotate(clusters=ArrayAgg(Coalesce("cluster_alias", "cluster_id"), distinct=True))

        # The Window annotation MUST happen after aggregations in Django 4.2 or later.
        # https://forum.djangoproject.com/t/django-4-2-behavior-change-when-using-arrayagg-on-unnested-arrayfield-postgresql-specific/21547
        rank_by_total = Window(expression=RowNumber(), order_by=rank_orders)
        ranks = ranks.annotate(rank=rank_by_total)

        rankings = []
        distinct_ranks = []
        for rank in ranks:
            rank_value = (rank.get(group) for group in group_by_value)
            if rank_value not in rankings:
                rankings.append(rank_value)
                distinct_ranks.append(rank)
        return self._ranked_list(data, distinct_ranks, set(rank_annotations))

    def _ranked_list(self, data_list, ranks, rank_fields=None):  # noqa C901
        """Get list of ranked items less than top.

        Args:
            data_list (List(Dict)): List of ranked data points from the same bucket
            ranks (List): list of ranks to use; overrides ranking that may present in data_list.
            rank_fields (Set): the fields on which ranking is performed.
        Returns:
            List(Dict): List of data points meeting the rank criteria

        """
        if not rank_fields:
            rank_fields = set()
        is_offset = "offset" in self.parameters.get("filter", {})
        group_by = self._get_group_by()
        self.max_rank = len(ranks)
        # Columns we drop in favor of the same named column merged in from rank data frame
        drop_columns = {"source_uuid"}
        if self.is_openshift:
            drop_columns.add("clusters")

        if not data_list:
            return data_list
        data_frame = pd.DataFrame(data_list)

        rank_data_frame = pd.DataFrame(ranks)
        rank_data_frame = rank_data_frame.drop(
            columns=["cost_total", "cost_total_distributed", "usage"], errors="ignore"
        )

        # Determine what to get values for in our rank data frame
        if self.is_aws and "account" in group_by:
            drop_columns.add("account_alias")
        if self.is_aws and "account" not in group_by:
            rank_data_frame = rank_data_frame.drop(columns=["account_alias"], errors="ignore")

        agg_fields = {}
        for col in [col for col in self.report_annotations if "units" in col]:
            drop_columns.add(col)
            agg_fields[col] = ["max"]

        aggs = data_frame.groupby(group_by, dropna=False).agg(agg_fields)
        columns = aggs.columns.droplevel(1)
        aggs.columns = columns
        aggs = aggs.reset_index()
        aggs = aggs.replace({np.nan: None})
        rank_data_frame = rank_data_frame.merge(aggs, on=group_by)

        # Create a dataframe of days in the query
        days = data_frame["date"].unique()
        day_data_frame = pd.DataFrame(days, columns=["date"])

        # Cross join ranks and days to get each field/rank for every day in th query
        ranks_by_day = rank_data_frame.merge(day_data_frame, how="cross")

        # add the ranking columns if they still exists in both dataframes
        rank_fields.intersection_update(set(ranks_by_day.columns.intersection(data_frame.columns)))
        if rank_fields:
            drop_columns.update(rank_fields)

        # Merge our data frame to "zero-fill" missing data for each rank field
        # per day in the query, using a RIGHT JOIN
        account_aliases = None
        merge_on = group_by + ["date"]
        if self.is_aws and "account" in group_by:
            account_aliases = data_frame[["account", "account_alias"]]
            account_aliases = account_aliases.drop_duplicates(subset="account")
        data_frame = data_frame.drop(columns=drop_columns, errors="ignore")
        data_frame = data_frame.merge(ranks_by_day, how="right", on=merge_on)

        if self.is_aws and "account" in group_by:
            data_frame = data_frame.drop(columns=["account_alias"], errors="ignore")
            data_frame = data_frame.merge(account_aliases, on="account", how="left")

        if is_offset:
            data_frame = data_frame[
                (data_frame["rank"] > self._offset) & (data_frame["rank"] <= (self._offset + self._limit))
            ]
        else:
            # Get others category
            others_data_frame = self._aggregate_ranks_over_limit(data_frame, group_by)
            # Reduce data to limit
            data_frame = data_frame[data_frame["rank"] <= self._limit]

            # Add the others category to the data set
            data_frame = pd.concat([data_frame, others_data_frame])

        # Replace NaN with 0
        numeric_columns = [col for col in self.report_annotations if "unit" not in col]
        fill_values = {column: 0 for column in numeric_columns}
        data_frame = data_frame.fillna(value=fill_values)

        # Finally replace any remaining NaN with None for JSON compatibility
        data_frame = data_frame.replace({np.nan: None})

        return data_frame.to_dict("records")

    def _aggregate_ranks_over_limit(self, data_frame, group_by):
        """When filter[limit] is used without filter[offset] we want to create an Others category."""
        drop_columns = group_by + ["rank", "source_uuid"]
        groups = ["date"]

        skip_columns = ["source_uuid", "gcp_project_alias", "clusters"]

        aggs = {
            col: ["max"] if "units" in col else ["sum"] for col in self.report_annotations if col not in skip_columns
        }
        others_data_frame = data_frame[data_frame["rank"] > self._limit]
        other_count = len(others_data_frame[group_by].drop_duplicates())

        source_uuids = list(others_data_frame["source_uuid"].explode().dropna().unique())
        if self.is_openshift:
            clusters = list(others_data_frame["clusters"].explode().dropna().unique())
            drop_columns.append("clusters")

        others_data_frame = others_data_frame.drop(columns=drop_columns, errors="ignore")
        others_data_frame = others_data_frame.groupby(groups, dropna=True).agg(aggs, axis=1)
        columns = others_data_frame.columns.droplevel(1)
        others_data_frame.columns = columns
        others_data_frame = others_data_frame.reset_index()

        # Add back columns
        other_str = "Others" if other_count > 1 else "Other"
        for group in group_by:
            others_data_frame[group] = other_str
            if is_grouped_by_project(self.parameters):
                if self._category:
                    others_data_frame["classification"] = "category"
                else:
                    others_data_frame["default_project"] = "False"
        if self.is_aws and "account" in group_by:
            others_data_frame["account_alias"] = other_str
        elif "gcp_project" in group_by:
            others_data_frame["gcp_project_alias"] = other_str

        others_data_frame["rank"] = self._limit + 1
        others_data_frame["source_uuid"] = [source_uuids] * len(others_data_frame)
        if self.is_openshift:
            others_data_frame["clusters"] = [clusters] * len(others_data_frame)

        return others_data_frame

    def date_group_data(self, data_list):
        """Group data by date."""
        date_grouped_data = defaultdict(list)
        account_alias_map = {}
        for data in data_list:
            key = data.get("date")
            alias = data.get("account_alias")
            if alias:
                account_alias_map[data.get("account")] = alias
            date_grouped_data[key].append(data)
        return date_grouped_data, account_alias_map

    def unpack_date_grouped_data(self, date_grouped_data):
        """Return date grouped data to a flatter form."""
        return_data = []
        for date, values in date_grouped_data.items():
            for value in values:
                return_data.append(value)
        return return_data

    def _create_previous_totals(self, previous_query, query_group_by):
        """Get totals from the time period previous to the current report.

        Args:
            previous_query (Query): A Django ORM query
            query_group_by (dict): The group by dict for the current report
        Returns:
            (dict) A dictionary keyed off the grouped values for the report

        """
        date_delta = self._get_date_delta()
        # Added deltas for each grouping
        # e.g. date, account, region, availability zone, et cetera
        delta_field = self._mapper._report_type_map.get("delta_key").get(self._delta)
        delta_annotation = {self._delta: delta_field}

        previous_sums = previous_query.values(*query_group_by).annotate(**delta_annotation)
        previous_dict = OrderedDict()
        for row in previous_sums:
            date = self.string_to_date(row["date"])
            date = date + date_delta
            row["date"] = self.date_to_string(date)
            key = tuple(row[key] for key in query_group_by)
            previous_dict[json_dumps(key)] = row[self._delta]

        return previous_dict

    def _get_previous_totals_filter(self, filter_dates):
        """Filter previous time range to exlude days from the current range.

        Specifically this covers days in the current range that have not yet
        happened, but that data exists for in the previous range.

        Args:
            filter_dates (list) A list of date strings of dates to filter

        Returns:
            (django.db.models.query_utils.Q) The OR date filter

        """
        date_delta = self._get_date_delta()
        prev_total_filters = None

        for i in range(len(filter_dates)):
            date = self.string_to_date(filter_dates[i])
            date = date - date_delta
            filter_dates[i] = self.date_to_string(date)

        for date in filter_dates:
            if prev_total_filters:
                prev_total_filters = prev_total_filters | Q(usage_start=date)
            else:
                prev_total_filters = Q(usage_start=date)
        return prev_total_filters

    def add_deltas(self, query_data, query_sum):
        """Calculate and add cost deltas to a result set.

        Args:
            query_data (list) The existing query data from execute_query
            query_sum (list) The sum returned by calculate_totals

        Returns:
            (dict) query data with new with keys "value" and "percent"

        """
        delta_group_by = ["date"] + self._get_group_by()
        delta_filter = self._get_filter(delta=True)
        previous_query = self.query_table.objects.filter(delta_filter).annotate(**self.annotations)
        previous_dict = self._create_previous_totals(previous_query, delta_group_by)
        for row in query_data:
            key = tuple(row[key] for key in delta_group_by)
            previous_total = previous_dict.get(json_dumps(key)) or 0
            current_total = row.get(self._delta) or 0
            row["delta_value"] = current_total - previous_total
            row["delta_percent"] = self._percent_delta(current_total, previous_total)
        # Calculate the delta on the total aggregate
        if self._delta in query_sum:
            if isinstance(query_sum.get(self._delta), dict):
                current_total_sum = Decimal(query_sum.get(self._delta, {}).get("value") or 0)
            else:
                current_total_sum = Decimal(query_sum.get(self._delta) or 0)
        else:
            if isinstance(query_sum.get("cost"), dict):
                current_total_sum = Decimal(query_sum.get("cost", {}).get("total").get("value") or 0)
            else:
                current_total_sum = Decimal(query_sum.get("cost") or 0)
        delta_field = self._mapper._report_type_map.get("delta_key").get(self._delta)
        prev_total_sum = previous_query.aggregate(value=delta_field)
        if self.resolution == "daily":
            dates = [entry.get("date") for entry in query_data]
            prev_total_filters = self._get_previous_totals_filter(dates)
            if prev_total_filters:
                prev_total_sum = previous_query.filter(prev_total_filters).aggregate(value=delta_field)

        prev_total_sum = Decimal(prev_total_sum.get("value") or 0)

        total_delta = current_total_sum - prev_total_sum
        total_delta_percent = self._percent_delta(current_total_sum, prev_total_sum)

        self.query_delta = {"value": total_delta, "percent": total_delta_percent}

        if self.order_field == "delta":
            reverse = True if self.order_direction == "desc" else False
            query_data = sorted(
                list(query_data), key=lambda x: (x.get("delta_value", 0), x.get("delta_percent", 0)), reverse=reverse
            )
        return query_data
