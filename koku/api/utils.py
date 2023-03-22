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
import pytz
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.utils import timezone
from tenant_schemas.utils import schema_context

from api.provider.models import Provider
from api.user_settings.settings import USER_SETTINGS
from koku.settings import KOKU_DEFAULT_COST_TYPE
from koku.settings import KOKU_DEFAULT_CURRENCY
from masu.config import Config
from masu.external.date_accessor import DateAccessor
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

    def __init__(self, utc=False):
        """Initialize when now is."""
        if utc:
            self._now = datetime.datetime.now(tz=pytz.UTC)
        else:
            self._now = timezone.now()

    @property
    def now(self):
        """Return current time at timezone."""
        return timezone.now()

    @property
    def now_utc(self):
        """Return current time at timezone."""
        return datetime.datetime.now(tz=pytz.UTC)

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
        return self._now.replace(microsecond=0, second=0, minute=0)

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
        return self._now.replace(microsecond=0, second=0, minute=0, hour=0)

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

    def month_start(self, in_date):
        """Datetime of midnight on the 1st of in_date month."""
        return in_date.replace(microsecond=0, second=0, minute=0, hour=0, day=1)

    def month_end(self, in_date):
        """Datetime of midnight on the last day of the in_date month."""
        month_end = self.days_in_month(in_date)
        if isinstance(in_date, datetime.datetime):
            return in_date.replace(microsecond=0, second=0, minute=0, hour=0, day=month_end)
        elif isinstance(in_date, datetime.date):
            return in_date.replace(day=month_end)

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

    def list_days(self, start_date, end_date):
        """Return a list of days from the start date til the end date.

        Args:
            start_date    (DateTime) starting datetime
            end_date      (DateTime) ending datetime
        Returns:
            (List[DateTime]): A list of days from the start date to end date

        """
        end_midnight = end_date
        start_midnight = start_date
        if isinstance(start_date, str):
            start_midnight = ciso8601.parse_datetime(start_date).replace(hour=0, minute=0, second=0, microsecond=0)
        if isinstance(end_date, str):
            end_midnight = ciso8601.parse_datetime(end_date).replace(hour=0, minute=0, second=0, microsecond=0)
        if isinstance(end_date, datetime.datetime):
            end_midnight = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        if isinstance(start_date, datetime.datetime):
            start_midnight = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        days = (end_midnight - start_midnight + self.one_day).days

        # built-in range(start, end, step) requires (start < end) == True
        day_range = range(days, 0) if days < 0 else range(0, days)
        output = [start_midnight + datetime.timedelta(i) for i in day_range]
        return output

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

    def list_month_tuples(self, start_date, end_date):
        """Return a list of tuples of datetimes.
        Like (first day of the month, last day of the month)
        from the start date til the end date.

        Args:
            start_date    (DateTime) starting datetime
            end_date      (DateTime) ending datetime
        Returns:
            List((DateTime, DateTime)): A list of months from the start date to end date

        """
        months = []
        dt_first = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_midnight = end_date.replace(hour=23, minute=59, second=59, microsecond=0)

        current = dt_first
        while current < end_midnight:
            num_days = self.days_in_month(current)
            months.append((current, current.replace(day=num_days)))
            next_month = current.replace(day=num_days) + self.one_day
            current = next_month
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
            bill_date = ciso8601.parse_datetime(bill_date).replace(tzinfo=pytz.UTC)
        date_obj = bill_date.strftime("%Y%m")
        return date_obj

    def bill_year_from_date(self, date):
        """Find the year from date."""

        if isinstance(date, str):
            date = ciso8601.parse_datetime(date).replace(tzinfo=pytz.UTC)
        date_obj = date.strftime("%Y")
        return date_obj

    def bill_month_from_date(self, date):
        """Find the month from date."""

        if isinstance(date, str):
            date = ciso8601.parse_datetime(date).replace(tzinfo=pytz.UTC)
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


def materialized_view_month_start(dh=DateHelper()):
    """Datetime of midnight on the first of the month where materialized summary starts."""
    return dh.this_month_start - relativedelta(months=settings.RETAIN_NUM_MONTHS - 1)


def get_months_in_date_range(report=None, start=None, end=None, invoice_month=None):
    """returns the month periods in a given date range from report"""
    dh = DateHelper()
    if report:
        if report.get("start") and report.get("end"):
            LOG.info(f"using start: {report.get('start')} and end: {report.get('end')} dates from manifest")
            start_date = report.get("start")
            end_date = report.get("end")
            if report.get("invoice_month"):
                LOG.info(f"using invoice_month: {report.get('invoice_month')}")
                invoice_month = report.get("invoice_month")
        else:
            LOG.info("generating start and end dates for manifest")
            start_date = DateAccessor().today() - datetime.timedelta(days=2)
            start_date = start_date.strftime("%Y-%m-%d")
            end_date = DateAccessor().today().strftime("%Y-%m-%d")
    elif invoice_month:
        if not end:
            end = dh.today.date().strftime("%Y-%m-%d")
        return [(start, end, invoice_month)]  # For report_data masu api
    else:
        start_date = start
        end_date = end

    # Grabbing ingest delta for initial ingest/summary
    summary_month = dh.today + relativedelta(months=-Config.INITIAL_INGEST_NUM_MONTHS)
    if start_date < summary_month.strftime("%Y-%m-01"):
        start_date = summary_month.strftime("%Y-%m-01")

    if end_date and end_date < summary_month.strftime("%Y-%m-%d"):
        end_date = dh.today.strftime("%Y-%m-%d")

    if report and report.get("provider_type") in [Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL]:
        return [(start_date, end_date, invoice_month)]

    start_date = ciso8601.parse_datetime(start_date).replace(tzinfo=pytz.UTC)
    end_date = ciso8601.parse_datetime(end_date).replace(tzinfo=pytz.UTC) if end_date else dh.today
    months = dh.list_month_tuples(start_date, end_date)

    num_months = len(months)
    first_month = months[0]
    months[0] = (start_date, first_month[1])

    last_month = months[num_months - 1]
    months[num_months - 1] = (last_month[0], end_date)

    # need to format all the datetimes into strings with the format "%Y-%m-%d" for the celery task
    for i, month in enumerate(months):
        start, end = month
        start_date = start.date().strftime("%Y-%m-%d")
        end_date = end.date().strftime("%Y-%m-%d")
        months[i] = (start_date, end_date, invoice_month)  # Invoice month is really only for GCP

    return months
