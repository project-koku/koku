#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Query Handling for all APIs."""
import datetime
import logging
from functools import cached_property

from dateutil import parser
from dateutil import relativedelta
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Case
from django.db.models import DecimalField
from django.db.models import Value
from django.db.models import When
from django.db.models.functions import TruncDay
from django.db.models.functions import TruncMonth

from api.currency.models import ExchangeRateDictionary
from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.report.constants import RESOLUTION_DAILY
from api.report.constants import TIME_SCOPE_UNITS_DAILY
from api.report.constants import TIME_SCOPE_VALUES_DAILY
from api.utils import DateHelper

LOG = logging.getLogger(__name__)
WILDCARD = "*"


class TruncMonthString(TruncMonth):
    """Class to handle string formated day truncation."""

    def convert_value(self, value, expression, connection):
        """Convert value to a string after super."""
        value = super().convert_value(value, expression, connection)
        return value.strftime("%Y-%m")


class TruncDayString(TruncDay):
    """Class to handle string formated day truncation."""

    def convert_value(self, value, expression, connection):
        """Convert value to a string after super."""
        value = super().convert_value(value, expression, connection)
        return value.strftime("%Y-%m-%d")


class QueryHandler:
    """Handles report queries and responses."""

    def __init__(self, parameters):
        """Establish query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        LOG.debug(f"Query Params: {parameters}")
        self.dh = DateHelper()
        parameters = self.filter_to_order_by(parameters)
        self.tenant = parameters.tenant
        self.access = parameters.access
        self.currency = parameters.currency
        self.parameters = parameters
        self.default_ordering = self._mapper._report_type_map.get("default_ordering")
        self.time_interval = []
        self._max_rank = 0

        self.time_scope_units = self.parameters.get_filter("time_scope_units")
        self.time_scope_value = (
            int(time_scope_value) if (time_scope_value := self.parameters.get_filter("time_scope_value")) else None
        )

        # self.start_datetime = parameters["start_date"]
        # self.end_datetime = parameters["end_date"]
        for param, attr in [("start_date", "start_datetime"), ("end_date", "end_datetime")]:
            p = self.parameters.get(param)
            if p:
                setattr(
                    self,
                    attr,
                    datetime.datetime.combine(parser.parse(p).date(), self.dh.midnight, tzinfo=settings.UTC),
                )
            else:
                setattr(self, attr, None)

        if self.resolution == "monthly":
            self.date_to_string = lambda dt: dt.strftime("%Y-%m")
            self.string_to_date = lambda dt: datetime.datetime.strptime(dt, "%Y-%m").date()
            self.date_trunc = TruncMonthString
            self.gen_time_interval = DateHelper().list_months
        else:
            self.date_to_string = lambda dt: dt.strftime("%Y-%m-%d")
            self.string_to_date = lambda dt: datetime.datetime.strptime(dt, "%Y-%m-%d").date()
            self.date_trunc = TruncDayString
            self.gen_time_interval = DateHelper().list_days

        if not (self.start_datetime or self.end_datetime):
            self._get_timeframe()

        self._create_time_interval()

    # FIXME: move this to a standalone utility function.
    @staticmethod
    def has_wildcard(in_list):
        """Check if list has wildcard.

        Args:
            in_list (List[String]): List of strings to check for wildcard
        Return:
            (Boolean): if wildcard is present in list

        """
        if isinstance(in_list, bool):
            return False
        if not in_list:
            return False
        return any(WILDCARD == item for item in in_list)

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

    @property
    def order(self):
        """Extract order_by parameter and apply ordering to the appropriate field.

        Returns:
            (String): Ordering value. Default is '-total'

        Example:
            `order_by[total]=asc` returns `total`
            `order_by[total]=desc` returns `-total`

        """
        order_map = {"asc": "", "desc": "-"}
        return f"{order_map[self.order_direction]}{self.order_field}"

    @property
    def order_field(self):
        """Order-by field name.

        The default is 'total'
        """
        order_by = self.parameters.get("order_by", self.default_ordering)
        return list(order_by.keys()).pop()

    @property
    def order_direction(self):
        """Order-by orientation value.

        Returns:
            (str) 'asc' or 'desc'; default is 'desc'

        """
        order_by = self.parameters.get("order_by", self.default_ordering)
        return list(order_by.values()).pop()

    @property
    def max_rank(self):
        """Return the max rank of a ranked list."""
        return self._max_rank

    @max_rank.setter
    def max_rank(self, max_rank):
        """Max rank setter."""
        self._max_rank = max_rank

    @property
    def resolution(self):
        """Extract resolution or provide default.

        Returns:
            (String): The value of how data will be sliced.

        """
        return self.parameters.get_filter("resolution", default=RESOLUTION_DAILY)

    def check_query_params(self, key, in_key):
        """Test if query parameters has a given key and key within it.

        Args:
        key     (String): key to check in query parameters
        in_key  (String): key to check if key is found in query parameters

        Returns:
            (Boolean): True if they keys given appear in given query parameters.

        """
        return self.parameters and key in self.parameters and in_key in self.parameters.get(key)  # noqa: W504

    def get_time_scope_units(self):
        """Extract time scope units or provide default.

        Returns:
            (String): The value of how data will be sliced.

        """
        if not self.time_scope_units:
            time_scope_units = self.parameters.get_filter("time_scope_units", default=TIME_SCOPE_UNITS_DAILY)
            self.time_scope_units = time_scope_units
        return self.time_scope_units

    def get_time_scope_value(self):
        """Extract time scope value or provide default.

        Returns:
            (Integer): time relative value providing query scope

        """
        if not self.time_scope_value:
            time_scope_value = self.parameters.get_filter("time_scope_value", default=TIME_SCOPE_VALUES_DAILY[0])
            self.time_scope_value = int(time_scope_value)
        return self.time_scope_value

    def _get_timeframe(self):
        """Obtain timeframe start and end dates.

        Returns:
            (DateTime): start datetime for query filter
            (DateTime): end datetime for query filter

        """
        time_scope_value = self.get_time_scope_value()
        time_scope_units = self.get_time_scope_units()
        start = None
        end = None
        if time_scope_units == "month":
            if time_scope_value == -1:
                # get current month
                start = self.dh.this_month_start
                end = self.dh.today
            elif time_scope_value == -3:
                start = self.dh.relative_month_start(-2)
                end = self.dh.month_end(start)
            else:
                # get previous month
                start = self.dh.last_month_start
                end = self.dh.last_month_end
        else:
            if time_scope_value == -10:
                # get last 10 days
                start = self.dh.n_days_ago(self.dh.this_hour, 9)
                end = self.dh.this_hour
            elif time_scope_value == -90:
                start = self.dh.n_days_ago(self.dh.this_hour, 89)
                end = self.dh.this_hour
            else:
                # get last 30 days
                start = self.dh.n_days_ago(self.dh.this_hour, 29)
                end = self.dh.this_hour

        self.start_datetime = start
        self.end_datetime = end
        return (self.start_datetime, self.end_datetime, self.time_interval)

    def _create_time_interval(self):
        """Create list of date times in interval.

        Returns:
            (List[DateTime]): List of all interval slices by resolution

        """
        self.time_interval = sorted(self.gen_time_interval(self.start_datetime, self.end_datetime))
        return self.time_interval

    def _get_date_delta(self):
        """Return a time delta."""
        if self.time_scope_value in [-1, -2, -3]:
            date_delta = relativedelta.relativedelta(months=1)
        elif self.time_scope_value in (-90, -30, -10):
            date_delta = datetime.timedelta(days=abs(self.time_scope_value))
        else:
            date_delta = datetime.timedelta(days=10)
        return date_delta

    def _get_time_based_filters(self, delta=False):
        if delta:
            date_delta = self._get_date_delta()
            start = self.start_datetime - date_delta
            end = self.end_datetime - date_delta
        else:
            start = self.start_datetime
            end = self.end_datetime

        start_filter = QueryFilter(field="usage_start", operation="gte", parameter=start.date())
        end_filter = QueryFilter(field="usage_start", operation="lte", parameter=end.date())
        return start_filter, end_filter

    def _get_filter(self, delta=False):
        """Create dictionary for filter parameters.

        Args:
            delta (Boolean): Construct timeframe for delta
        Returns:
            (Dict): query filter dictionary

        """
        filters = QueryFilterCollection()

        # add time constraint filters
        start_filter, end_filter = self._get_time_based_filters(delta)
        filters.add(query_filter=start_filter)
        filters.add(query_filter=end_filter)

        return filters

    def _get_gcp_filter(self, delta=False):
        """Create dictionary for filter parameters for GCP.

        GCP filtering is a little different because we need the invoice
        month filter, and pad the time range to include cross over data.

        Args:
            delta (Boolean): Construct timeframe for delta
        Returns:
            (Dict): query filter dictionary
        """
        filters = QueryFilterCollection()
        if delta:
            date_delta = self._get_date_delta()
            start = self.start_datetime - date_delta
            end = self.end_datetime - date_delta
            invoice_months = self.dh.gcp_find_invoice_months_in_date_range(start.date(), end.date())
        else:
            start = self.start_datetime
            end = self.end_datetime
            invoice_months = self.dh.gcp_find_invoice_months_in_date_range(start.date(), end.date())
            # We add a 5 day buffer to the start & end here
            # to handle cross over data. We may want to change
            # this to an env in the future
            if self.parameters.get_filter("time_scope_value") and self.time_scope_value in [-1, -2, -3]:
                start = self.dh.n_days_ago(start, 5)
                end = self.dh.n_days_ahead(end, 5)

        invoice_filter = QueryFilter(field="invoice_month", operation="in", parameter=invoice_months)
        filters.add(invoice_filter)
        start_filter = QueryFilter(field="usage_start", operation="gte", parameter=start.date())
        end_filter = QueryFilter(field="usage_start", operation="lte", parameter=end.date())
        filters.add(query_filter=start_filter)
        filters.add(query_filter=end_filter)
        return filters

    def filter_to_order_by(self, parameters):  # noqa: C901
        """Remove group_by[NAME]=* and replace it with group_by[NAME]=X.

        The parameters object contains a list of filters and a list of group_bys.

        For example, if the parameters object contained the following:
        group_by[X] = Y
        group_by[Z] = *     # removes this line
        filter[Z] = L
        filter[X] = Y

        The returned parameters object would contain lists that look like this:

        group_by[X] = Y
        group_by[Z] = L     # adds this line
        filter[Z] = L
        filter[X] = Y

        Thereby removing the star when there is a filter provided.

        Args:
            parameters (QueryParameters): The parameters object

        Returns:
            parameters (QueryParameters): The parameters object

        """
        # find if there is a filter[key]=value that matches this group_by[key]=value
        for key, value in parameters.parameters.get("group_by", {}).items():
            if self.has_wildcard(value):
                filter_value = parameters.parameters.get("filter", {}).get(key)
                if filter_value:
                    parameters.parameters["group_by"][key] = filter_value
        return parameters

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
        if not isinstance(filt, list):
            filt = [filt]
        for _filt in filt:
            check_field_type = None
            try:
                if hasattr(self, "query_table"):
                    # Reports APIs
                    check_field_type = self.query_table._meta.get_field(_filt.get("field", "")).get_internal_type()
                elif hasattr(self, "data_sources"):
                    # Tags APIs
                    check_field_type = (
                        self.data_sources[0]
                        .get("db_table")
                        ._meta.get_field(_filt.get("field", ""))
                        .get_internal_type()
                    )
            except FieldDoesNotExist:
                pass

            _filt["operation"] = "contains" if check_field_type == "ArrayField" else "in"
            q_filter = QueryFilter(parameter=access, **_filt)
            filters.add(q_filter)
