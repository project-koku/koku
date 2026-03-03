#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Timezone utilities for provider-aware date handling.

Design notes:
- Always store provider timezone as an IANA string (e.g. 'America/New_York').
- Use zoneinfo (stdlib since 3.9) — no pytz dependency, correct DST handling.
- The Trino helper centralises the AT TIME ZONE expression so every SQL template
  stays in sync.
- Falls back to UTC silently so existing UTC providers see zero change.
"""
import logging
import re
from datetime import date
from datetime import datetime
from datetime import timezone
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError

from api.common import log_json

LOG = logging.getLogger(__name__)

# Characters permitted in an IANA timezone string — guards against SQL injection
# when the value is interpolated into Trino templates via | sqlsafe.
_ALLOWED_TZ_RE = re.compile(r"^[A-Za-z0-9_/+\-]{1,64}$")

# AWS region → IANA timezone mapping.
# Covers all billing-significant regions; extend as new regions are added.
AWS_REGION_TO_TZ: dict[str, str] = {
    "us-east-1": "America/New_York",
    "us-east-2": "America/Chicago",
    "us-west-1": "America/Los_Angeles",
    "us-west-2": "America/Los_Angeles",
    "ca-central-1": "America/Toronto",
    "eu-west-1": "Europe/Dublin",
    "eu-west-2": "Europe/London",
    "eu-west-3": "Europe/Paris",
    "eu-central-1": "Europe/Berlin",
    "eu-north-1": "Europe/Stockholm",
    "ap-southeast-1": "Asia/Singapore",
    "ap-southeast-2": "Australia/Sydney",
    "ap-northeast-1": "Asia/Tokyo",
    "ap-northeast-2": "Asia/Seoul",
    "ap-south-1": "Asia/Kolkata",
    "sa-east-1": "America/Sao_Paulo",
    "me-south-1": "Asia/Dubai",
    "af-south-1": "Africa/Johannesburg",
    # fallback
    "default": "UTC",
}


def sanitize_timezone_for_sql(tz_name: str) -> str:
    """Return tz_name if safe for Trino SQL interpolation, otherwise 'UTC'.

    This is the second line of defence after serializer-level IANA validation.
    """
    if not tz_name or not _ALLOWED_TZ_RE.match(tz_name):
        LOG.warning(log_json(msg="unsafe timezone value, falling back to UTC", timezone=tz_name))
        return "UTC"
    return tz_name


def get_provider_timezone(provider_uuid: str) -> ZoneInfo:
    """Return ZoneInfo for the given provider UUID.

    Falls back to UTC on any error so callers are never blocked.
    """
    # Import here to avoid circular imports at module load time.
    from api.provider.models import Provider  # noqa: PLC0415

    try:
        provider = Provider.objects.get(uuid=provider_uuid)
        tz_name = provider.timezone or "UTC"
        return ZoneInfo(tz_name)
    except Provider.DoesNotExist:
        LOG.warning(log_json(msg="provider not found for timezone lookup", provider_uuid=str(provider_uuid)))
        return ZoneInfo("UTC")
    except ZoneInfoNotFoundError:
        LOG.warning(
            log_json(
                msg="unknown timezone on provider, falling back to UTC",
                provider_uuid=str(provider_uuid),
            )
        )
        return ZoneInfo("UTC")


def normalize_datetime_to_provider_tz(dt: datetime, provider_tz: ZoneInfo) -> datetime:
    """Convert a UTC-aware (or naive-UTC) datetime to provider local time.

    Args:
        dt: datetime — naive assumed UTC, or already timezone-aware.
        provider_tz: ZoneInfo for the provider's billing timezone.

    Returns:
        datetime in provider local time.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(provider_tz)


def utc_range_for_provider_local_day(
    local_date: date, provider_tz: ZoneInfo
) -> tuple[datetime, datetime]:
    """Return the UTC [start, end) window that covers one provider-local calendar day.

    Example — 2024-01-01 in America/New_York (UTC-5 in winter):
        start = 2024-01-01T05:00:00Z
        end   = 2024-01-02T05:00:00Z

    Use this to expand SQL WHERE clauses so they capture all UTC rows that
    belong to the provider's local billing day.
    """
    from datetime import timedelta  # noqa: PLC0415

    local_midnight = datetime(local_date.year, local_date.month, local_date.day, tzinfo=provider_tz)
    next_midnight = local_midnight + timedelta(days=1)
    return local_midnight.astimezone(timezone.utc), next_midnight.astimezone(timezone.utc)


def aws_region_to_tz(region_code: str) -> str:
    """Map an AWS region code to an IANA timezone string.

    **Design note — best-effort inference:**
    Region codes are the most reliable per-provider signal available without
    customer-provided metadata.  However, billing timezone is technically
    where the *account was created*, which is not always the same as the
    deployment region.  Treat this mapping as a best-effort starting point;
    the Provider.timezone field can be overridden via the API or management
    command if the inferred value is wrong.

    Follow-up: request infra/ops to verify inferred timezones for all
    production accounts before enabling non-UTC summarisation.

    Args:
        region_code: e.g. 'us-east-1'

    Returns:
        IANA timezone string, e.g. 'America/New_York'. Falls back to 'UTC'.
    """
    return AWS_REGION_TO_TZ.get(region_code, AWS_REGION_TO_TZ["default"])


def trino_date_expr(timestamp_col: str, provider_tz: str) -> str:
    """Build the Trino SQL expression for extracting a provider-local date.

    When provider_tz is UTC the expression is the minimal ``date(<col>)`` so
    there is no runtime cost for the common case.

    Args:
        timestamp_col: Trino column expression (e.g. 'lineitem_usagestartdate').
        provider_tz:   IANA timezone string from Provider.timezone.

    Returns:
        SQL fragment, e.g.:
            "date(lineitem_usagestartdate AT TIME ZONE 'America/New_York')"
    """
    safe_tz = sanitize_timezone_for_sql(provider_tz or "UTC")
    if safe_tz == "UTC":
        return f"date({timestamp_col})"
    return f"date({timestamp_col} AT TIME ZONE '{safe_tz}')"
