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

"""Unit conversion util functions."""

import calendar
import datetime
from pprint import pformat

import pint
from django.conf import settings
from django.db.models import Model
from django.utils import timezone
from pint.errors import UndefinedUnitError


class DateHelper():
    """Helper class with convenience functions."""

    def __init__(self):
        """Initialize when now is."""
        self._now = timezone.now()

    @property
    def now(self):
        """Return current time at timezone."""
        return timezone.now()

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
        return self.this_hour.replace(microsecond=0, second=0,
                                      minute=0, hour=0, day=1)

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

    def next_month(self, in_date):
        """Return the first of the next month from the in_date.

        Args:
            in_date    (DateTime) input datetime
        Returns:
            (DateTime): First of the next month

        """
        num_days = self.days_in_month(in_date)
        dt_next_month = in_date.replace(day=num_days, hour=0, minute=0,
                                        second=0, microsecond=0) + self.one_day
        return dt_next_month

    def previous_month(self, in_date):
        """Return the first of the previous month from the in_date.

        Args:
            in_date    (DateTime) input datetime
        Returns:
            (DateTime): First of the previous month

        """
        dt_prev_month = in_date.replace(day=1, hour=0, minute=0,
                                        second=0, microsecond=0) - self.one_day
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

    def list_days(self, start_date, end_date):
        """Return a list of days from the start date til the end date.

        Args:
            start_date    (DateTime) starting datetime
            end_date      (DateTime) ending datetime
        Returns:
            (List[DateTime]): A list of days from the start date to end date

        """
        end_midnight = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        start_midnight = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        days = (end_midnight - start_midnight + self.one_day).days
        return [start_midnight + datetime.timedelta(i) for i in range(days)]

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

    def days_in_month(self, date):
        """Return the number of days in the month.

        Args:
            date (datetime.datetime)

        Returns:
            (int) number of days in the month

        """
        # monthrange returns (day_of_week, num_days)
        _, num_days = calendar.monthrange(date.year, date.month)
        return num_days


class UnitConverter:
    """Utility class to do unit conversion."""

    def __init__(self):
        """Initialize the UnitConverter."""
        self.unit_registry = pint.UnitRegistry()
        self.Quantity = self.unit_registry.Quantity

    def validate_unit(self, unit):
        """Validate that the unit type exists in the registry.

        Args:
            unit (str): The unit type being checked

        Returns:
            (str) The validated unit

        """
        try:
            getattr(self.unit_registry, str(unit))
        except (AttributeError, UndefinedUnitError):
            try:
                getattr(self.unit_registry, str(unit.lower()))
            except (AttributeError, UndefinedUnitError) as err:
                raise err
            else:
                return unit.lower()

        return str(unit)

    def convert_quantity(self, value, from_unit, to_unit):
        """Convert a quantity between comparable units.

        Args:
            value (Any numeric type): The magnitude of the quantity
            from_unit (str): The starting unit to convert from
            to_unit (str): The ending unit to conver to

        Returns:
            (pint.Quantity): A quantity with both magnitude and unit

        Example:
            >>> uc = UnitConverter()
            >>> result = uc.covert_quantity(1.2, 'gigabyte', 'byte')
            >>> result
            <Quantity(1200000000.0, 'byte')>
            >>> print(result.magnitude)
            1200000000.0
            >>> print(result.units)
            byte

        """
        from_unit = self.validate_unit(from_unit)
        to_unit = self.validate_unit(to_unit)
        return self.Quantity(value, from_unit).to(to_unit)


# pylint: disable=protected-access
def stringify(obj):
    """Return a human-readable string using a model object's fields."""
    out = {'class': obj.__class__}
    for field in obj._meta.fields:
        # TODO: add a way to redact sensitive fields.
        attr = str(field).split('.')[-1]
        out[attr] = getattr(obj, attr)
    return pformat(out)


class PrintableModelMixIn:
    """Mix-in for enabling django.db.Model classes to print their field names and values.

    Caution: there is no way to exclude fields or field data. This is intended
    to be used only for development and debugging.
    """

    def __repr__(self):
        """Unambiguous object representation.

        Returns: (dict) a representation of the model's fields and data.
        """
        if settings.DEVELOPMENT:
            return stringify(self)
        return super().__repr__()

    def __str__(self):
        """Object string representation.

        Returns: (str) a string representation of the model's fields and data.
        """
        if settings.DEVELOPMENT:
            return stringify(self)
        return super().__str__()
