#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Query Handling for Organizations."""
import copy
import logging
import operator
from functools import reduce

from django.db.models import F
from django.db.models import Q
from django.db.models.functions import Coalesce
from django_tenants.utils import tenant_context

from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.query_handler import QueryHandler

LOG = logging.getLogger(__name__)


class OrgQueryHandler(QueryHandler):
    """Handles organizations queries and responses.

    Subclasses need to define a `data_sources` class attribute that defines the
    model objects and fields where the tagging information is stored.

    Definition:

        # a list of dicts
        data_sources = [{}, {}]

        # each dict has this structure
        dict = { 'db_table': Object,
                 'db_column': str,
                 'type': str
               }

        db_table = (Object) the model object containing tags
        db_column = (str) the field on the model containing tags
        type = (str) [optional] the type of tagging information, used for filtering

    Example:
        MyCoolTagHandler(OrgQueryHandler):
            data_sources = [{'db_table': MyFirstTagModel,
                             'db_column': 'awesome_tags',
                             'type': 'awesome'},
                            {'db_table': MySecondTagModel,
                             'db_column': 'schwifty_tags',
                             'type': 'neato'}]

    """

    provider = "ORGS"
    data_sources = []
    SUPPORTED_FILTERS = []
    FILTER_MAP = {}

    def __init__(self, parameters):
        """Establish org query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        super().__init__(parameters)
        # _set_start_and_end_dates must be called after super and before _get_filter
        if not self.parameters.get("start_date") and not self.parameters.get("end_date"):
            self._set_start_and_end_dates()
        # super() needs to be called before calling _get_filter()
        self.query_filter = self._get_filter()

    def _set_start_and_end_dates(self):
        """Set start and end dates.

        Start date must be the first of the month. This function checks the
        time_scope_value and sets the start date to either current month
        start or previous month start.

        """
        time_scope = int(self.parameters.get_filter("time_scope_value"))
        if time_scope not in (-10, -30):
            return
        month_start = self.dh.this_month_start
        if self.dh.n_days_ago(self.dh.today, -(time_scope + 1)) > month_start:
            self.start_datetime = month_start
        else:
            self.start_datetime = self.dh.last_month_start
        self.end_datetime = self.dh.today

    def _format_query_response(self):
        """Format the query response with data.

        Returns:
            (Dict): Dictionary response of query params, data

        """
        output = copy.deepcopy(self.parameters.parameters)
        output["data"] = self.query_data
        return output

    def _get_filter(self, delta=False):  # noqa: C901
        """Create dictionary for filter parameters.

        Args:
            delta (Boolean): Construct timeframe for delta
        Returns:
            (Dict): query filter dictionary

        """
        filters = QueryFilterCollection()

        for filter_key in self.SUPPORTED_FILTERS:
            filter_value = self.parameters.get_filter(filter_key)
            if filter_value and not OrgQueryHandler.has_wildcard(filter_value):
                filter_obj = self.FILTER_MAP.get(filter_key)
                for item in filter_value:
                    q_filter = QueryFilter(parameter=item, **filter_obj)
                    filters.add(q_filter)

        # Update filters that specifiy and or or in the query parameter
        and_composed_filters = self._set_operator_specified_filters("and")
        or_composed_filters = self._set_operator_specified_filters("or")
        exact_composed_filters = self._set_operator_specified_filters("exact")
        final_filters = filters.compose() & and_composed_filters & or_composed_filters & exact_composed_filters

        LOG.debug(f"_get_filter: {final_filters}")
        return final_filters

    def _set_operator_specified_filters(self, operator):
        """Set any filters using AND instead of OR."""
        filters = QueryFilterCollection()
        composed_filter = Q()
        for filter_key in self.SUPPORTED_FILTERS:
            operator_key = f"{operator}:{filter_key}"
            filter_value = self.parameters.get_filter(operator_key)
            logical_operator = operator
            if filter_value and len(filter_value) < 2 and logical_operator != "exact":
                logical_operator = "or"
            if filter_value and not OrgQueryHandler.has_wildcard(filter_value):
                filter_obj = self.FILTER_MAP.get(filter_key)
                if isinstance(filter_obj, list):
                    for _filt in filter_obj:
                        filt_filters = QueryFilterCollection()
                        for item in filter_value:
                            q_filter = QueryFilter(parameter=item, logical_operator=logical_operator, **_filt)
                            filt_filters.add(q_filter)
                        composed_filter = composed_filter | filt_filters.compose()
                else:
                    for item in filter_value:
                        q_filter = QueryFilter(parameter=item, logical_operator=logical_operator, **filter_obj)
                        filters.add(q_filter)
        if filters:
            composed_filter = composed_filter & filters.compose()

        return composed_filter

    def _get_sub_ou_list(self, data, org_ids):
        """Get a list of the sub org units for a org unit."""
        level = data.get("level")
        level = level + 1
        unit_path = data.get("org_unit_path")
        final_sub_ou_list = []
        with tenant_context(self.tenant):
            for source in self.data_sources:
                # Grab columns for this query
                account_info = source.get("account_alias_column")
                level_column = source.get("level_column")
                org_path = source.get("org_path_column")
                # Build filters
                filters = QueryFilterCollection()
                no_accounts = QueryFilter(field=f"{account_info}", operation="isnull", parameter=True)
                filters.add(no_accounts)
                exact_parent_id = QueryFilter(field=f"{level_column}", operation="exact", parameter=level)
                filters.add(exact_parent_id)
                path_on_like = QueryFilter(field=f"{org_path}", operation="icontains", parameter=unit_path)
                filters.add(path_on_like)
                composed_filters = filters.compose()
                # Start quering
                sub_org_query = source.get("db_table").objects
                sub_org_query = sub_org_query.filter(composed_filters)
                sub_org_query = sub_org_query.filter(id__in=org_ids)
                sub_ou_list = sub_org_query.values_list("org_unit_id", flat=True)
                final_sub_ou_list.extend(sub_ou_list)
        return final_sub_ou_list

    def _create_accounts_mapping(self):
        """Returns a mapping of org ids to accounts."""
        account_mapping = {}
        with tenant_context(self.tenant):
            for source in self.data_sources:
                # Grab columns for this query
                account_info = source.get("account_alias_column")
                # Create filters & Query
                filters = QueryFilterCollection()
                no_org_units = QueryFilter(field=f"{account_info}", operation="isnull", parameter=False)
                filters.add(no_org_units)
                composed_filters = filters.compose()
                account_query = source.get("db_table").objects
                account_query = account_query.filter(composed_filters)
                account_query = account_query.exclude(deleted_timestamp__lte=self.start_datetime)
                account_query = account_query.exclude(created_timestamp__gt=self.end_datetime)
                if self.access:
                    accounts_to_filter = self.access.get("aws.account", {}).get("read", [])
                    if accounts_to_filter and "*" not in accounts_to_filter:
                        account_query = account_query.filter(account_alias__account_id__in=accounts_to_filter)
                account_query = account_query.order_by(f"{account_info}", "-created_timestamp")
                account_query = account_query.distinct(f"{account_info}")
                account_query = account_query.annotate(
                    alias=Coalesce(F(f"{account_info}__account_alias"), F(f"{account_info}__account_id"))
                )
                for account in account_query:
                    org_id = account.org_unit_id
                    alias = account.alias
                    if account_mapping.get(org_id):
                        account_list = account_mapping[org_id]
                        account_list.append(alias)
                        account_mapping[org_id] = account_list
                    else:
                        account_mapping[org_id] = [alias]
        return account_mapping

    def get_org_units(self):
        """Get a list of org keys to build upon."""
        org_units = list()
        org_id_list = list()
        with tenant_context(self.tenant):
            for source in self.data_sources:
                # Grab columns for this query
                org_id = source.get("org_id_column")
                org_path = source.get("org_path_column")
                org_name = source.get("org_name_column")
                level = source.get("level_column")
                account_info = source.get("account_alias_column")
                created_field = source.get("created_time_column")
                # Create filters & Query
                account_filter = QueryFilterCollection()
                no_accounts = QueryFilter(field=f"{account_info}", operation="isnull", parameter=True)
                account_filter.add(no_accounts)
                remove_accounts = account_filter.compose()
                org_unit_query = source.get("db_table").objects
                org_unit_query = org_unit_query.filter(remove_accounts)
                org_unit_query = org_unit_query.exclude(deleted_timestamp__lte=self.start_datetime)
                org_unit_query = org_unit_query.exclude(created_timestamp__gt=self.end_datetime)
                val_list = [org_id, org_name, org_path, level]
                org_unit_query = org_unit_query.order_by(f"{org_id}", f"-{created_field}").distinct(f"{org_id}")
                org_ids = org_unit_query.values_list("id", flat=True)
                if self.access:
                    acceptable_ous = self.access.get("aws.organizational_unit", {}).get("read", [])
                    if acceptable_ous and "*" not in acceptable_ous:
                        allowed_ids_query = source.get("db_table").objects
                        allowed_ids_query = allowed_ids_query.filter(
                            reduce(operator.or_, (Q(org_unit_path__icontains=rbac) for rbac in acceptable_ous))
                        ).filter(remove_accounts)
                        allowed_ids = allowed_ids_query.values_list("id", flat=True)
                        org_ids = list(set(org_ids) & set(allowed_ids))
                        org_unit_query = org_unit_query.filter(id__in=org_ids)
                org_id_list.extend(org_ids)
                # Note: you want to collect the org_id_list before you implement the self.query_filter
                # so that way the get_sub_ou list will still work when you do filter[org_unit_id]=OU_002
                if self.query_filter:
                    org_unit_query = org_unit_query.filter(self.query_filter)
                org_unit_query = org_unit_query.values(*val_list)
                org_units.extend(org_unit_query)
        return org_units, org_id_list

    def execute_query(self):
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params and data

        """
        query_data, org_id_list = self.get_org_units()
        if not self.parameters.get("key_only"):
            accounts_mapping = self._create_accounts_mapping()
            for data in query_data:
                org_id = data.get("org_unit_id")
                data["sub_orgs"] = self._get_sub_ou_list(data, org_id_list)
                data["accounts"] = accounts_mapping.get(org_id, [])

        self.query_data = query_data
        return self._format_query_response()
