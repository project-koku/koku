import calendar
import datetime


def ocp_volume_calc(unit, hours, month=None):
    """Function used in raw calc tests for calculating volume cost data."""
    current_time = datetime.datetime.now(datetime.timezone.utc)
    month = month if month else current_time.month
    byte_seconds = 3600 * unit * (1024 * 1024 * 1024)
    byte_seconds_daily = byte_seconds * hours
    seconds_in_day = 60 * 60 * 24
    days_in_month = calendar.monthrange(current_time.year, month)[1]
    gig_per_byte = 1 / (1024 * 1024 * 1024)
    value = (byte_seconds_daily / seconds_in_day) / days_in_month * gig_per_byte
    return value
