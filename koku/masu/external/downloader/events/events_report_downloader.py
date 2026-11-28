#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""HTTP pull downloader for koku-events daily cost rollups."""
import json
import logging

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from providers.events.provider import resolve_events_endpoint

LOG = logging.getLogger(__name__)

MAX_DATES_PER_REQUEST = 366


class EventsReportDownloaderError(Exception):
    """Error raised while pulling export data from koku-events."""


class EventsReportDownloader:
    """Stateless HTTP client for koku-events /api/v1/export/{dirty-dates,daily}."""

    def __init__(self, credentials=None, data_source=None, timeout=None):
        self.base_url, self.auth_token, self.ca_cert = resolve_events_endpoint(credentials, data_source)
        self.timeout = timeout or getattr(settings, "COST_EVENTS_HTTP_TIMEOUT", 60)
        self.verify = self.ca_cert if self.ca_cert else True
        self._session = self._build_session()

    def _build_session(self):
        retries = Retry(
            total=3,
            allowed_methods={"GET"},
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        session = requests.Session()
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _headers(self, accept="application/json"):
        headers = {
            "Accept": accept,
            "Accept-Encoding": "gzip",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def _require_base_url(self):
        if not self.base_url:
            raise EventsReportDownloaderError("Events source base URL is not configured.")

    def fetch_dirty_dates(self, since=None, tenant_id=None):
        """Fetch snapshot watermark and dirty UTC dates from koku-events.

        Returns:
            tuple[str, list[str]]: (watermark_rfc3339, sorted_dates_yyyy_mm_dd)
        """
        self._require_base_url()
        url = f"{self.base_url}/api/v1/export/dirty-dates"
        params = {}
        if since:
            params["since"] = since
        if tenant_id:
            params["tenant_id"] = tenant_id

        try:
            resp = self._session.get(
                url,
                headers=self._headers(accept="application/json"),
                params=params,
                timeout=self.timeout,
                verify=self.verify,
            )
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as err:
            raise EventsReportDownloaderError(f"Failed to fetch dirty dates from {url}: {err}") from err

        watermark = payload.get("watermark")
        dates = payload.get("dates")
        if not isinstance(dates, list):
            raise EventsReportDownloaderError(f"Malformed dirty-dates response from {url}: missing 'dates' list")
        return watermark, sorted({str(d) for d in dates if d})

    def fetch_daily_rollups(self, dates, tenant_id=None):
        """Stream NDJSON daily cost rollup rows for the requested UTC dates.

        Chunks requests to MAX_DATES_PER_REQUEST dates per HTTP call.

        Returns:
            list[dict]: Parsed rollup row dictionaries.
        """
        self._require_base_url()
        if not dates:
            return []

        url = f"{self.base_url}/api/v1/export/daily"
        rows = []
        for idx in range(0, len(dates), MAX_DATES_PER_REQUEST):
            chunk = dates[idx : idx + MAX_DATES_PER_REQUEST]
            params = {
                "dates": ",".join(chunk),
                "format": "ndjson",
            }
            if tenant_id:
                params["tenant_id"] = tenant_id

            try:
                resp = self._session.get(
                    url,
                    headers=self._headers(accept="application/x-ndjson"),
                    params=params,
                    timeout=self.timeout,
                    verify=self.verify,
                    stream=True,
                )
                resp.raise_for_status()
                for raw_line in resp.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue
                    line = raw_line.strip()
                    if not line:
                        continue
                    rows.append(json.loads(line))
            except (requests.RequestException, ValueError) as err:
                raise EventsReportDownloaderError(f"Failed to fetch daily rollups from {url}: {err}") from err

        return rows
