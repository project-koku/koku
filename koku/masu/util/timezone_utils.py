#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Timezone utilities for provider-aware date handling.

Design notes (corrected after mentor review — 2026-03):
- AWS CUR, GCP BigQuery billing export, and Azure Cost Details all publish
  timestamps in UTC.  No AT TIME ZONE conversion is applied in Trino SQL.
- ``Provider.timezone`` is retained for future OpenShift / UI-display features.
- sanitize_timezone_for_sql and get_provider_timezone are kept for those
  future callers and for any non-cloud providers that may need local-time
  attribution (e.g. on-premise OCP with a known local clock).
- Use zoneinfo (stdlib since 3.9) — no pytz dependency, correct DST handling.
- Falls back to UTC silently so existing providers see zero change.
"""
import logging
import re
from datetime import datetime
from datetime import timezone
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError

from api.common import log_json

LOG = logging.getLogger(__name__)

# Characters permitted in an IANA timezone string — guards against SQL injection
# when the value is interpolated into Trino templates via | sqlsafe.
_ALLOWED_TZ_RE = re.compile(r"^[A-Za-z0-9_/+\-]{1,64}$")

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
    except ZoneInfoNotFoundError:
        LOG.warning(
            log_json(
                msg="unknown timezone on provider, falling back to UTC",
                provider_uuid=str(provider_uuid),
            )
        )
        return ZoneInfo("UTC")
    except Exception:  # noqa: BLE001 — covers DoesNotExist and unexpected DB errors
        LOG.warning(log_json(msg="provider timezone lookup failed, falling back to UTC", provider_uuid=str(provider_uuid)))
        return ZoneInfo("UTC")


def normalize_datetime_to_provider_tz(dt: datetime, provider_tz: ZoneInfo) -> datetime:
    """Convert a UTC-aware (or naive-UTC) datetime to provider local time.

    Useful for display / UI features that show costs in the provider's
    local time.  Cloud billing SQL pipelines use plain date() since all
    cloud providers export timestamps in UTC.

    Args:
        dt: datetime — naive assumed UTC, or already timezone-aware.
        provider_tz: ZoneInfo for the provider's billing timezone.

    Returns:
        datetime in provider local time.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(provider_tz)
