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
"""Query Handling for Organizations."""
import copy
import logging

from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import F
from django.db.models import Q
from django.db.models.functions import Coalesce
from tenant_schemas.utils import tenant_context

from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.query_handler import QueryHandler
from api.utils import DateHelper


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

    dh = DateHelper()

    def __init__(self, parameters):
        """Establish org query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        super().__init__(parameters)
        # _set_start_and_end_dates must be called after super and before _get_filter
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
        composed_filters = filters.compose()
        filter_list = [composed_filters, and_composed_filters, or_composed_filters]
        final_filters = None
        for filter_option in filter_list:
            if filter_option:
                if final_filters is not None:
                    final_filters & filter_option
                else:
                    final_filters = filter_option

        LOG.debug(f"_get_filter: {final_filters}")
        return final_filters

    def _set_operator_specified_filters(self, operator):
        """Set any filters using AND instead of OR."""
        filters = QueryFilterCollection()
        composed_filter = Q()
        for filter_key in self.SUPPORTED_FILTERS:
            operator_key = operator + ":" + filter_key
            filter_value = self.parameters.get_filter(operator_key)
            logical_operator = operator
            if filter_value and len(filter_value) < 2:
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

    def _get_sub_ou_list(self, data):
        """Get a list of the sub org units for a org unit."""
        level = data.get("level")
        level = level + 1
        unit_path = data.get("org_unit_path")
        with tenant_context(self.tenant):
            for source in self.data_sources:
                # Grab columns for this query
                account_info = source.get("account_alias_column")
                level_column = source.get("level_column")
                org_id = source.get("org_id_column")
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
                sub_org_query = sub_org_query.exclude(deleted_timestamp__lte=self.start_datetime)
                sub_org_query = sub_org_query.exclude(created_timestamp__gte=self.end_datetime)
                if self.query_filter:
                    sub_org_query = sub_org_query.filter(self.query_filter)
                val_list = [level_column]
                sub_org_query = sub_org_query.values(*val_list)
                sub_org_query = sub_org_query.annotate(subs_list=ArrayAgg(f"{org_id}", distinct=True))
        if sub_org_query:
            return sub_org_query[0].get("subs_list", [])
        else:
            return []

    def _get_accounts_list(self, org_id):
        """Returns an account list for given org_id."""
        with tenant_context(self.tenant):
            for source in self.data_sources:
                # Grab columns for this query
                account_info = source.get("account_alias_column")
                org_id_column = source.get("org_id_column")
                org_name = source.get("org_name_column")
                org_path = source.get("org_path_column")
                # Create filters & Query
                filters = QueryFilterCollection()
                no_org_units = QueryFilter(field=f"{account_info}", operation="isnull", parameter=False)
                filters.add(no_org_units)
                exact_org_id = QueryFilter(field=f"{org_id_column}", operation="exact", parameter=org_id)
                filters.add(exact_org_id)
                composed_filters = filters.compose()
                account_query = source.get("db_table").objects
                account_query = account_query.filter(composed_filters)
                account_query = account_query.exclude(deleted_timestamp__lte=self.start_datetime)
                account_query = account_query.exclude(created_timestamp__gte=self.end_datetime)
                if self.query_filter:
                    account_query = account_query.filter(self.query_filter)
                val_list = [org_name, org_id_column, org_path]
                account_query = account_query.values(*val_list)
                account_query = account_query.annotate(
                    alias_list=ArrayAgg(
                        Coalesce(F(f"{account_info}__account_alias"), F(f"{account_info}__account_id")), distinct=True
                    )
                )
        if account_query:
            return account_query[0].get("alias_list", [])
        else:
            return []

    def get_org_units(self):
        """Get a list of org keys to build upon."""
        org_units = list()
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
                filters = QueryFilterCollection()
                no_accounts = QueryFilter(field=f"{account_info}", operation="isnull", parameter=True)
                filters.add(no_accounts)
                composed_filters = filters.compose()
                org_unit_query = source.get("db_table").objects
                org_unit_query = org_unit_query.filter(composed_filters)
                org_unit_query = org_unit_query.exclude(deleted_timestamp__lte=self.start_datetime)
                org_unit_query = org_unit_query.exclude(created_timestamp__gte=self.end_datetime)
                val_list = [org_id, org_name, org_path, level]
                if self.query_filter:
                    org_unit_query = org_unit_query.filter(self.query_filter)
                org_unit_query = org_unit_query.values(*val_list)
                org_unit_query = org_unit_query.order_by(f"{org_id}", f"-{created_field}").distinct(f"{org_id}")
                org_units.extend(org_unit_query)
        return org_units

    def execute_query(self):
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params and data

        """
        query_data = self.get_org_units()

        if not self.parameters.get("key_only"):
            for data in query_data:
                org_id = data.get("org_unit_id")
                data["sub_orgs"] = self._get_sub_ou_list(data)
                data["accounts"] = self._get_accounts_list(org_id)

        self.query_data = query_data
        return self._format_query_response()
