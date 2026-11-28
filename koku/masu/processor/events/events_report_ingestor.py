#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Pull ingestor and built-in source provisioning for Events (koku-events)."""
import datetime
import logging
from collections import defaultdict
from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.utils import timezone
from django_tenants.utils import schema_context

from api.common import log_json
from api.iam.models import Customer
from api.provider.models import Provider
from api.provider.models import ProviderAuthentication
from api.provider.models import ProviderBillingSource
from api.provider.models import Sources
from koku.cache import EVENTS_CACHE_PREFIX
from koku.cache import invalidate_cache_for_tenant_and_cache_key
from koku.cache import SOURCES_CACHE_PREFIX
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.events_report_db_accessor import _to_date
from masu.database.events_report_db_accessor import EventsReportDBAccessor
from masu.external.downloader.events.events_report_downloader import EventsReportDownloader
from masu.processor import is_events_source_enabled
from masu.processor.events.events_report_summary_updater import EventsReportSummaryUpdater
from masu.processor.report_summary_updater import enable_cloud_bill_currencies
from reporting.provider.models import TenantAPIProvider
from reporting_common.models import CostUsageReportManifest

LOG = logging.getLogger(__name__)

BUILTIN_EVENTS_SOURCE_NAME = "Cost Events"


def ensure_builtin_events_source():
    """Ensure every tenant has a built-in Events Provider when COST_EVENTS_URL is set.

    Idempotent: creates once per customer and updates data_source.url if changed.
    """
    events_url = getattr(settings, "COST_EVENTS_URL", "")
    if not events_url:
        return []

    ensured = []
    for customer in Customer.objects.all():
        if not is_events_source_enabled(customer.schema_name):
            continue

        existing = Provider.objects.filter(
            customer=customer,
            type=Provider.PROVIDER_EVENTS,
        ).first()
        if existing:
            ds = dict(getattr(existing.billing_source, "data_source", None) or {})
            if ds.get("url") != events_url:
                ds["url"] = events_url
                if existing.billing_source:
                    existing.billing_source.data_source = ds
                    existing.billing_source.save(update_fields=["data_source"])
            ensured.append(existing)
            continue

        auth = ProviderAuthentication.objects.create(credentials={})
        billing_source = ProviderBillingSource.objects.create(data_source={"url": events_url})
        provider = Provider(
            name=BUILTIN_EVENTS_SOURCE_NAME,
            type=Provider.PROVIDER_EVENTS,
            authentication=auth,
            billing_source=billing_source,
            customer=customer,
            setup_complete=True,
            active=True,
        )
        # Skip Provider.save()'s automatic check_report_updates enqueue; sync_events_sources polls directly.
        super(Provider, provider).save()

        with schema_context(customer.schema_name):
            TenantAPIProvider.objects.get_or_create(
                uuid=provider.uuid,
                defaults={"name": provider.name, "type": provider.type},
            )

        if not Sources.objects.filter(koku_uuid=provider.uuid).exists():
            next_id = (Sources.objects.order_by("-source_id").first().source_id + 1) if Sources.objects.exists() else 1
            next_offset = (Sources.objects.order_by("-offset").first().offset + 1) if Sources.objects.exists() else 1
            Sources.objects.create(
                source_id=next_id,
                source_uuid=provider.uuid,
                name=provider.name,
                source_type=Provider.PROVIDER_EVENTS,
                authentication={"credentials": {}},
                billing_source={"data_source": {"url": events_url}},
                koku_uuid=provider.uuid,
                account_id=customer.account_id,
                org_id=customer.org_id,
                offset=next_offset,
            )

        invalidate_cache_for_tenant_and_cache_key(customer.schema_name, SOURCES_CACHE_PREFIX)
        LOG.info(
            log_json(
                msg="provisioned built-in Events source",
                schema=customer.schema_name,
                provider_uuid=str(provider.uuid),
                url=events_url,
            )
        )
        ensured.append(provider)

    return ensured


class EventsReportIngestor:
    """Watermark-driven HTTP pull sync from koku-events into Koku PostgreSQL."""

    def __init__(self, provider: Provider, downloader=None):
        self.provider = provider
        self.schema_name = provider.customer.schema_name
        self.credentials = getattr(provider.authentication, "credentials", None) or {}
        self.data_source = getattr(provider.billing_source, "data_source", None) or {}
        self.downloader = downloader or EventsReportDownloader(
            credentials=self.credentials,
            data_source=self.data_source,
        )

    def _get_markup_rate(self):
        with CostModelDBAccessor(
            self.schema_name, self.provider.uuid, price_list_effective_on=None
        ) as cost_model_accessor:
            markup = cost_model_accessor.markup or {}
            return Decimal(str(markup.get("value", 0))) / Decimal(100)

    def _record_manifests(self, dirty_dates, now):
        dates_by_month = defaultdict(list)
        for d in dirty_dates:
            day = _to_date(d)
            month_start = datetime.datetime(day.year, day.month, 1, 0, 0, 0, tzinfo=settings.UTC)
            dates_by_month[month_start].append(day)

        for month_start, days in dates_by_month.items():
            assembly_id = f"events-{month_start.strftime('%Y-%m')}"
            manifest, _ = CostUsageReportManifest.objects.get_or_create(
                provider=self.provider,
                assembly_id=assembly_id,
                defaults={
                    "billing_period_start_datetime": month_start,
                    "num_total_files": len(days),
                    "creation_datetime": now,
                    "completed_datetime": now,
                    "export_datetime": now,
                },
            )
            manifest.num_total_files = len(days)
            manifest.completed_datetime = now
            manifest.export_datetime = now
            manifest.save(
                update_fields=[
                    "num_total_files",
                    "completed_datetime",
                    "export_datetime",
                ]
            )

    def sync(self):
        """Execute one incremental watermark sync cycle for this Events provider.

        Returns:
            dict: Sync summary (dirty_dates, row_count, watermark).
        """
        if not is_events_source_enabled(self.schema_name):
            LOG.info(
                log_json(
                    msg="Events source flag disabled; skipping sync",
                    schema=self.schema_name,
                    provider_uuid=str(self.provider.uuid),
                )
            )
            return {"skipped": True, "dirty_dates": [], "row_count": 0, "watermark": None}

        additional_ctx = dict(self.provider.additional_context or {})
        last_watermark = additional_ctx.get("events_watermark")
        tenant_id = self.data_source.get("tenant_id")

        new_watermark, dirty_dates = self.downloader.fetch_dirty_dates(
            since=last_watermark,
            tenant_id=tenant_id,
        )
        rows = self.downloader.fetch_daily_rollups(dirty_dates, tenant_id=tenant_id) if dirty_dates else []
        markup_value = self._get_markup_rate()

        with EventsReportDBAccessor(self.schema_name) as accessor:
            bill_ids, min_date, max_date = accessor.replace_daily_summary_for_dates(
                provider_uuid=self.provider.uuid,
                dirty_dates=dirty_dates,
                rows=rows,
                markup_value=markup_value,
                provider_name=self.provider.name,
                provider_type=self.provider.type,
            )

        if min_date and max_date:
            updater = EventsReportSummaryUpdater(self.schema_name, self.provider)
            updater.update_summary_tables(min_date, max_date)
            try:
                enable_cloud_bill_currencies(self.schema_name, self.provider, start_date=min_date, end_date=max_date)
            except Exception as err:
                LOG.warning(
                    log_json(
                        msg="failed to enable Events bill currencies",
                        schema=self.schema_name,
                        provider_uuid=str(self.provider.uuid),
                        error=str(err),
                    )
                )

        now = timezone.now()
        if dirty_dates and rows:
            self._record_manifests(dirty_dates, now)

        if new_watermark:
            additional_ctx["events_watermark"] = new_watermark
        self.provider.additional_context = additional_ctx
        self.provider.setup_complete = True
        self.provider.polling_timestamp = now
        self.provider.data_updated_timestamp = now
        self.provider.save(
            update_fields=["additional_context", "setup_complete", "polling_timestamp", "data_updated_timestamp"]
        )

        invalidate_cache_for_tenant_and_cache_key(self.schema_name, EVENTS_CACHE_PREFIX)
        invalidate_cache_for_tenant_and_cache_key(self.schema_name, SOURCES_CACHE_PREFIX)

        result = {
            "skipped": False,
            "dirty_dates": dirty_dates,
            "row_count": len(rows),
            "bill_ids": bill_ids,
            "watermark": new_watermark,
            "tracing_id": str(uuid4()),
        }
        LOG.info(
            log_json(
                msg="Events sync completed",
                schema=self.schema_name,
                provider_uuid=str(self.provider.uuid),
                dirty_dates_count=len(dirty_dates),
                row_count=len(rows),
                watermark=new_watermark,
            )
        )
        return result
