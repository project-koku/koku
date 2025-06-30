#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Unit conversion util functions."""
import calendar
import datetime
import logging
from datetime import timedelta

import ciso8601
from dateutil import parser
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import schema_context

from api.settings.settings import USER_SETTINGS
from koku.settings import KOKU_DEFAULT_COST_TYPE
from koku.settings import KOKU_DEFAULT_CURRENCY
from masu.config import Config
from reporting.user_settings.models import UserSettings

LOG = logging.getLogger(__name__)


def get_cost_type(request):
    """get cost_type from the DB user settings table or sets cost_type to default if table is empty."""

    with schema_context(request.user.customer.schema_name):
        query_settings = UserSettings.objects.first()
        if not query_settings:
            cost_type = KOKU_DEFAULT_COST_TYPE
        else:
            cost_type = query_settings.settings["cost_type"]
    return cost_type


def get_currency(request):
    """get currency from the DB user settings table or sets currency to default if table is empty."""
    currency = KOKU_DEFAULT_CURRENCY
    if not request:
        return currency
    with schema_context(request.user.customer.schema_name):
        query_settings = UserSettings.objects.first()
        if query_settings:
            currency = query_settings.settings["currency"]
        return currency


def get_account_settings(request):
    """Returns users settings from the schema or the default settings"""
    with schema_context(request.user.customer.schema_name):
        query_settings = UserSettings.objects.first()
    if query_settings:
        return query_settings
    return USER_SETTINGS


def merge_dicts(*list_of_dicts):
    """Merge a list of dictionaries and combine common keys into a list of values.

    args:
        list_of_dicts: a list of dictionaries. values within the dicts must be lists
            dict = {key: [values]}

    """
    output = {}
    for dikt in list_of_dicts:
        for k, v in dikt.items():
            if not output.get(k):
                output[k] = v
            else:
                output[k].extend(v)
                output[k] = list(set(output[k]))
    return output


class DateHelper:
    """Helper class with convenience functions."""

    def __init__(self):
        """Initialize when now is."""
        self._now = None

    @property
    def now(self):
        """Return current time at timezone."""
        return self._now or timezone.now()

    @property
    def now_utc(self):
        """Return current time at timezone."""
        return datetime.datetime.now(tz=settings.UTC)

    @property
    def midnight(self):
        """Return a time object set to midnight."""
        return datetime.time(0, 0, 0, 0)

    @property
    def one_day(self):
        """Timedelta of one day."""
        return datetime.timedelta(days=1)

    @property
    def one_hour(self):
        """Timedelta of one hour."""
        return datetime.timedelta(minutes=60)

    @property
    def this_hour(self):
        """Datetime of top of the current hour."""
        return self.now.replace(microsecond=0, second=0, minute=0)

    @property
    def next_hour(self):
        """Datetime of top of the next hour."""
        next_hour = (self.this_hour + self.one_hour).hour
        return self.this_hour.replace(hour=next_hour)

    @property
    def previous_hour(self):
        """Datetime of top of the previous hour."""
        prev_hour = (self.this_hour - self.one_hour).hour
        return self.this_hour.replace(hour=prev_hour)

    @property
    def today(self):
        """Datetime of midnight today."""
        return self.now.replace(microsecond=0, second=0, minute=0, hour=0)

    @property
    def yesterday(self):
        """Datetime of midnight yesterday."""
        return self.today - self.one_day

    @property
    def tomorrow(self):
        """Datetime of midnight tomorrow."""
        return self.today + self.one_day

    @property
    def this_month_start(self):
        """Datetime of midnight on the 1st of this month."""
        return self.this_hour.replace(microsecond=0, second=0, minute=0, hour=0, day=1)

    @property
    def last_month_start(self):
        """Datetime of midnight on the 1st of the previous month."""
        last_month = self.this_month_start - self.one_day
        return last_month.replace(day=1)

    @property
    def next_month_start(self):
        """Datetime of midnight on the 1st of next month."""
        return self.this_month_end + self.one_day

    @property
    def this_month_end(self):
        """Datetime of midnight on the last day of this month."""
        month_end = self.days_in_month(self.this_month_start)
        return self.this_month_start.replace(day=month_end)

    @property
    def last_month_end(self):
        """Datetime of midnight on the last day of the previous month."""
        month_end = self.days_in_month(self.last_month_start)
        return self.last_month_start.replace(day=month_end)

    @property
    def next_month_end(self):
        """Datetime of midnight on the last day of next month."""
        month_end = self.days_in_month(self.next_month_start)
        return self.next_month_start.replace(day=month_end)

    def create_end_of_life_date(self, year: int, month: int, day: int) -> datetime:
        """Creates a deprecation or sunset date for endpoints."""
        date = datetime.datetime(year, month, day, tzinfo=settings.UTC)
        date_at_midnight = date.replace(microsecond=0, second=0, minute=0, hour=0)
        return date_at_midnight

    def month_start(self, in_date):
        """Datetime of midnight on the 1st of in_date month."""
        if isinstance(in_date, datetime.datetime):
            return in_date.replace(microsecond=0, second=0, minute=0, hour=0, day=1)
        elif isinstance(in_date, datetime.date):
            return in_date.replace(day=1)
        elif isinstance(in_date, str):
            return parser.parse(in_date).date().replace(day=1)

    def month_start_utc(self, in_date):
        """Datetime of midnight on the 1st of in_date month with a UTC timezone included."""
        return self.month_start(in_date).replace(tzinfo=settings.UTC)

    def month_end(self, in_date):
        """Datetime of midnight on the last day of the in_date month."""
        if isinstance(in_date, str):
            in_date = parser.parse(in_date).date()
        month_end = self.days_in_month(in_date)
        if isinstance(in_date, datetime.datetime):
            return in_date.replace(microsecond=0, second=0, minute=0, hour=0, day=month_end)
        return in_date.replace(day=month_end)

    def parse_to_date(self, date_input):
        """Convert input into a date object if it is a string or datetime.

        Args:
            date_input (str | datetime.datetime): The input to be converted into a date.

        Returns:
          datetime.date: A date object parsed from the input.
        """

        if isinstance(date_input, str):
            return datetime.datetime.strptime(date_input, "%Y-%m-%d").date()
        if isinstance(date_input, datetime.datetime):
            return date_input.date()
        return date_input

    def next_month(self, in_date):
        """Return the first of the next month from the in_date.

        Args:
            in_date    (DateTime) input datetime
        Returns:
            (DateTime): First of the next month

        """
        num_days = self.days_in_month(in_date)
        dt_next_month = in_date.replace(day=num_days, hour=0, minute=0, second=0, microsecond=0) + self.one_day
        return dt_next_month

    def previous_month(self, in_date):
        """Return the first of the previous month from the in_date.

        Args:
            in_date    (DateTime) input datetime
        Returns:
            (DateTime): First of the previous month

        """
        dt_prev_month = in_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - self.one_day
        return dt_prev_month.replace(day=1)

    def set_datetime_utc(self, in_date):
        """Return datetime with utc.
        Args:
            in_date    (datetime, date, string) input datetime
        Returns:
            (datetime): date in the past
        """
        if isinstance(in_date, datetime.date):
            in_date = datetime.datetime(in_date.year, in_date.month, in_date.day)
        if isinstance(in_date, str):
            in_date = ciso8601.parse_datetime(in_date).replace(hour=0, minute=0, second=0, microsecond=0)

        in_date.replace(tzinfo=settings.UTC)

        return in_date

    def n_days_ago(self, in_date, n_days):
        """Return midnight of the n days from the in_date in past.

        Args:
            in_date    (DateTime) input datetime
            n_days     (integer) number of days in the past
        Returns:
            (DateTime): A day n days in the past

        """
        midnight = in_date.replace(hour=0, minute=0, second=0, microsecond=0)
        n_days = midnight - datetime.timedelta(days=n_days)
        return n_days

    def n_days_ahead(self, in_date, n_days):
        """Return midnight of the n days from the in_date in future.

        Args:
            in_date    (DateTime) input datetime
            n_days     (integer) number of days in the past
        Returns:
            (DateTime): A day n days in the past

        """
        midnight = in_date.replace(hour=0, minute=0, second=0, microsecond=0)
        n_days = midnight + datetime.timedelta(days=n_days)
        return n_days

    def list_days(
        self,
        start_date: datetime.datetime | datetime.date | str,
        end_date: datetime.datetime | datetime.date | str,
    ) -> list[datetime.date]:
        """Return a list of days from the start date til the end date.

        Args:
            start_date    (DateTime) starting datetime
            end_date      (DateTime) ending datetime
        Returns:
            (List[DateTime]): A list of days from the start date to end date

        """
        if isinstance(start_date, str):
            start_date = ciso8601.parse_datetime(start_date).date()
        if isinstance(end_date, str):
            end_date = ciso8601.parse_datetime(end_date).date()
        if isinstance(start_date, datetime.datetime):
            start_date = start_date.date()
        if isinstance(end_date, datetime.datetime):
            end_date = end_date.date()
        days = (end_date - start_date + self.one_day).days

        # built-in range(start, end, step) requires (start < end) == True
        day_range = range(days, 0) if days < 0 else range(days)
        return [start_date + datetime.timedelta(i) for i in day_range]

    def list_months(self, start_date, end_date):
        """Return a list of months from the start date til the end date.

        Args:
            start_date    (DateTime) starting datetime
            end_date      (DateTime) ending datetime
        Returns:
            (List[DateTime]): A list of months from the start date to end date

        """
        months = []
        dt_first = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_midnight = end_date.replace(hour=23, minute=59, second=59, microsecond=0)

        current = dt_first
        while current < end_midnight:
            months.append(current)
            num_days = self.days_in_month(current)
            next_month = current.replace(day=num_days) + self.one_day
            current = next_month
        return months

    def list_month_tuples(
        self, start_date: datetime.date, end_date: datetime.date
    ) -> list[tuple[datetime.date, datetime.date]]:
        """Return a list of month range tuples with precise start/end dates.

        The first tuple uses the actual start_date, the last tuple uses the actual end_date,
        and middle months (if any) use full month boundaries.

        Args:
            start_date    (datetime.date) starting datetime
            end_date      (datetime.date) ending datetime
        Returns:
            List((datetime.date, datetime.date)): A list of (start, end) tuples for each month period

        """
        if start_date > end_date:
            return []

        months = []
        current_start = to_date(start_date)
        final_end = to_date(end_date)

        while current_start <= final_end:
            # Calculate the end of current month
            current_month_end = self.month_end(current_start)

            # Determine the actual end date for this period
            if current_month_end <= final_end:
                # Full month or partial month ending before final_end
                period_end = current_month_end
            else:
                # Last partial month - use the actual end date
                period_end = final_end

            months.append((current_start, period_end))

            # If we've reached the final month, break
            if period_end >= final_end:
                break

            # Move to start of next month
            current_start = current_start + relativedelta(day=31) + relativedelta(days=1)

        return months

    def days_in_month(self, date, year=None, month=None):
        """Return the number of days in the month.

        Args:
            date (datetime.datetime)

        Returns:
            (int) number of days in the month

        """
        # monthrange returns (day_of_week, num_days)
        if year and month:
            _, num_days = calendar.monthrange(year, month)
        else:
            _, num_days = calendar.monthrange(date.year, date.month)
        return num_days

    def relative_month_start(self, month_seek, dt=None):
        """Return start of month for month_seek months in the past or future.
        Params:
            month_seek (int)      : months to seek. Negative is past, positive is future
            dt         (datetime) : start datetime. Default is today
        Returns:
            (datetime)            : Datetime result of operation
        """
        if dt is None:
            dt = self.today

        rel_month_delta = relativedelta(months=month_seek)
        return self.month_start(dt + rel_month_delta)

    def relative_month_end(self, month_seek, dt=None):
        """Return end of month for month_seek months in the past or future.
        Params:
            month_seek (int)      : months to seek. Negative is past, positive is future
            dt         (datetime) : start datetime. Default is today
        Returns:
            (datetime)            : Datetime result of operation
        """
        if dt is None:
            dt = self.today

        rel_month_delta = relativedelta(months=month_seek)
        return self.month_end(dt + rel_month_delta)

    def invoice_month_start(self, date_str):
        """Find the beginning of the month for invoice month.

        Invoice month format is {year}{month}.
        Ex. 202011

        Args:
            date_str: invoice month format

        Returns:
            (datetime.datetime)
        """
        if not isinstance(date_str, str):
            date_str = str(date_str)
        date_obj = datetime.datetime.strptime(date_str, "%Y%m")
        month_start = self.month_start(date_obj)
        return month_start

    def invoice_month_from_bill_date(self, bill_date):
        """Find the beginning of the month for invoice month.

        Invoice month format is {year}{month}.
        Ex. 202011

        Args:
            bill_date: Start of the month for the bill.

        Returns:
            (datetime.datetime)
        """
        if isinstance(bill_date, str):
            bill_date = ciso8601.parse_datetime(bill_date).replace(tzinfo=settings.UTC)
        date_obj = bill_date.strftime("%Y%m")
        return date_obj

    def bill_year_from_date(self, date):
        """Find the year from date."""

        if isinstance(date, str):
            date = ciso8601.parse_datetime(date).replace(tzinfo=settings.UTC)
        date_obj = date.strftime("%Y")
        return date_obj

    def bill_month_from_date(self, date):
        """Find the month from date."""

        if isinstance(date, str):
            date = ciso8601.parse_datetime(date).replace(tzinfo=settings.UTC)
        date_obj = date.strftime("%m")
        return date_obj

    def gcp_find_invoice_months_in_date_range(self, start, end):
        """Finds all the invoice months in a given date range.

        GCP invoice month format is {year}{month}.
        Ex. 202011

        Args:
            start: (datetime.datetime)
            end: (datetime.datetime)

        Returns:
            List of invoice months.
        """
        # Add a little buffer to end date for beginning of the month
        # searches for invoice_month for dates < end_date
        end_range = end + timedelta(1)
        invoice_months = []
        for day in range((end_range - start).days):
            invoice_month = (start + timedelta(day)).strftime("%Y%m")
            if invoice_month not in invoice_months:
                invoice_months.append(invoice_month)
        return invoice_months

    def get_year_month_list_from_start_end(self, start, end):
        if isinstance(start, datetime.date):
            start = datetime.datetime(start.year, start.month, start.day, tzinfo=settings.UTC)
        if isinstance(end, datetime.date):
            end = datetime.datetime(end.year, end.month, end.day, tzinfo=settings.UTC)
        dates = self.list_months(start, end)
        return [{"year": date.strftime("%Y"), "month": date.strftime("%m")} for date in dates]


def materialized_view_month_start(dh=DateHelper()):
    """Datetime of midnight on the first of the month where materialized summary starts."""
    return dh.this_month_start - relativedelta(months=settings.RETAIN_NUM_MONTHS - 1)


def to_date(date_input: str | datetime.datetime | datetime.date | None) -> datetime.date | None:
    """Convert a string, date, or datetime to a date object.

    Args:
        date_input: A date string, datetime object, date object, or None

    Returns:
        A date object, or None if input is None

    Raises:
        ValueError: If the input string cannot be parsed as a date
        TypeError: If the input type is not supported
    """
    if date_input is None:
        return None

    if isinstance(date_input, str):
        return parser.parse(date_input).date()

    if isinstance(date_input, datetime.datetime):
        return date_input.date()

    if isinstance(date_input, datetime.date):
        return date_input

    raise TypeError(f"Expected str, datetime, date, or None, got {type(date_input)}")


def get_months_in_date_range(
    start: str | datetime.datetime | None = None,
    end: str | datetime.datetime | None = None,
    invoice_month: str | None = None,
    *,
    report: bool = False,
) -> list[tuple[datetime.datetime, datetime.datetime, str | None]]:
    """returns the month periods in a given date range from report"""
    dh = DateHelper()
    today_date = dh.today.date()

    # Converting inputs to datetime objects
    dt_start = to_date(start)
    dt_end = to_date(end)

    dt_invoice_month = invoice_month

    if report:
        if dt_start and dt_end:
            LOG.info(f"using start: {dt_start} and end: {dt_end} dates from manifest")
            if dt_invoice_month:
                LOG.info(f"using invoice_month: {dt_invoice_month}")
        else:
            LOG.info("generating start and end dates for manifest")
            dt_start = today_date - datetime.timedelta(days=2) if today_date.day > 2 else today_date.replace(day=1)
            dt_end = today_date

    elif dt_invoice_month:
        dt_start = dt_start or today_date
        dt_end = dt_end or today_date

        # For report_data masu API
        return [(dt_start, dt_end, dt_invoice_month)]

    # Grabbing ingest delta for initial ingest/summary
    summary_month = (today_date - relativedelta(months=Config.INITIAL_INGEST_NUM_MONTHS)).replace(day=1)
    if not dt_start or dt_start < summary_month:
        dt_start = summary_month.replace(day=1)

    if not dt_end or dt_end < summary_month:
        dt_end = today_date

    if report and dt_invoice_month:
        return [(dt_start, dt_end, dt_invoice_month)]

    months = dh.list_month_tuples(dt_start, dt_end)
    return [(start, end, dt_invoice_month) for start, end in months]
