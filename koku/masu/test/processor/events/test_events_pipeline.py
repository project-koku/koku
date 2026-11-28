#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""End-to-end tests for the Phase 1 Events (koku-events) pull ingestion pipeline."""
from datetime import date
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock
from unittest.mock import patch

import requests
from django.test.utils import override_settings
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from api.provider.models import Provider
from api.provider.models import ProviderAuthentication
from api.provider.models import ProviderBillingSource
from api.provider.models import Sources
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from koku.celery import EVENTS_SYNC_BEAT_NAME
from koku.celery import register_events_sync_beat
from masu.database.events_report_db_accessor import EventsReportDBAccessor
from masu.external.downloader.events.events_report_downloader import EventsReportDownloader
from masu.external.downloader.events.events_report_downloader import EventsReportDownloaderError
from masu.processor.cost_model_cost_updater import CostModelCostUpdater
from masu.processor.events.events_report_db_cleaner import EventsReportDBCleaner
from masu.processor.events.events_report_db_cleaner import EventsReportDBCleanerError
from masu.processor.events.events_report_ingestor import ensure_builtin_events_source
from masu.processor.events.events_report_ingestor import EventsReportIngestor
from masu.processor.expired_data_remover import ExpiredDataRemover
from masu.test import MasuTestCase
from providers.events.provider import EventsLocalProvider
from providers.events.provider import EventsProvider
from providers.provider_access import ProviderAccessor
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.all.models import TagMapping
from reporting.provider.events.models import EventsCostEntryBill
from reporting.provider.events.models import EventsCostEntryLineItemDailySummary
from reporting.provider.events.models import EventsCostSummaryByProjectP
from reporting.provider.events.models import EventsCostSummaryByServiceP
from reporting.provider.events.models import EventsCostSummaryByTenantP
from reporting.provider.events.models import EventsCostSummaryP
from reporting.provider.events.models import EventsTagsSummary
from reporting.provider.events.models import EventsTagsValues
from reporting.provider.events.models import EventsUsageSummaryByMeterP
from reporting_common.models import CostUsageReportManifest
from sources.api.serializers import AdminSourcesSerializer
from sources.api.source_type_views import SourceTypesView


class EventsProviderAndDownloaderTest(MasuTestCase):
    """Test EventsProvider reachability, Sources gating, and EventsReportDownloader."""

    def test_provider_accessor_resolves_events(self):
        """ProviderAccessor resolves Events and Events-local providers."""
        self.assertEqual(ProviderAccessor(Provider.PROVIDER_EVENTS).service_name(), Provider.PROVIDER_EVENTS)
        self.assertEqual(
            ProviderAccessor(Provider.PROVIDER_EVENTS_LOCAL).service_name(), Provider.PROVIDER_EVENTS_LOCAL
        )
        self.assertTrue(EventsLocalProvider().cost_usage_source_is_reachable({}, {}))

    @override_settings(COST_EVENTS_URL="")
    def test_events_provider_requires_url(self):
        """Missing URL raises ValidationError."""
        with self.assertRaises(ValidationError):
            EventsProvider().cost_usage_source_is_reachable({}, {})

    @patch("providers.events.provider.requests.get")
    def test_events_provider_reachability_success_and_auth_error(self, mock_get):
        """Reachability sends Bearer token and fails on 401/network errors."""
        ok_resp = MagicMock(status_code=200)
        ok_resp.raise_for_status.return_value = None
        mock_get.return_value = ok_resp

        self.assertTrue(
            EventsProvider().cost_usage_source_is_reachable(
                {"token": "secret-tok"}, {"url": "http://cost-events:8020", "tenant_id": "t-1"}
            )
        )
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret-tok")
        self.assertEqual(kwargs["params"], {"tenant_id": "t-1"})

        unauth_resp = MagicMock(status_code=401)
        mock_get.return_value = unauth_resp
        with self.assertRaises(ValidationError):
            EventsProvider().cost_usage_source_is_reachable({"token": "bad"}, {"url": "http://cost-events:8020"})

        mock_get.side_effect = requests.ConnectionError("refused")
        with self.assertRaises(ValidationError):
            EventsProvider().cost_usage_source_is_reachable({}, {"url": "http://cost-events:8020"})

    @override_settings(ONPREM=True, COST_EVENTS_URL="http://cost-events:8020")
    def test_onprem_sources_allow_events_when_cost_events_url_set(self):
        """When ONPREM=True and COST_EVENTS_URL is set, Events source type is exposed and accepted."""
        factory = APIRequestFactory()
        resp = SourceTypesView.as_view()(factory.get("/source_types"))
        self.assertEqual(resp.status_code, 200)
        names = {st["name"] for st in resp.data["data"]}
        self.assertEqual(names, {"openshift", "events"})

        serializer = AdminSourcesSerializer()
        # Should not raise for Events when enabled; still rejects AWS on-prem.
        serializer._validate_onprem_source_type(Provider.PROVIDER_EVENTS)
        with self.assertRaises(ValidationError):
            serializer._validate_onprem_source_type(Provider.PROVIDER_AWS)

    def test_downloader_fetch_dirty_dates_and_ndjson_rollups(self):
        """EventsReportDownloader parses dirty-dates JSON and streams NDJSON rollups."""
        dl = EventsReportDownloader(
            credentials={"token": "export-secret"},
            data_source={"url": "http://cost-events:8020"},
        )
        dirty_resp = MagicMock()
        dirty_resp.raise_for_status.return_value = None
        dirty_resp.json.return_value = {
            "watermark": "2026-11-27T12:00:00Z",
            "dates": ["2026-11-27", "2026-11-26"],
        }
        daily_resp = MagicMock()
        daily_resp.raise_for_status.return_value = None
        daily_resp.iter_lines.return_value = [
            (
                '{"usage_date":"2026-11-26","tenant_id":"t1","service":"compute_instance",'
                '"meter":"compute","cost_type":"Infrastructure","usage_amount":"3600",'
                '"unit":"seconds","cost_amount":"1.50","currency":"USD",'
                '"tags":{"env":"prod"},"entry_count":60}'
            ),
            "",
            (
                '{"usage_date":"2026-11-27","tenant_id":"t1","service":"custom_gpu",'
                '"meter":"gpu_s","cost_type":"Supplementary","usage_amount":"-10",'
                '"unit":"seconds","cost_amount":"-0.50","currency":"USD",'
                '"tags":{},"entry_count":1}'
            ),
        ]

        with patch.object(dl._session, "get", side_effect=[dirty_resp, daily_resp]) as mock_get:
            watermark, dates = dl.fetch_dirty_dates(since="2026-11-25T00:00:00Z")
            rows = dl.fetch_daily_rollups(dates)

        self.assertEqual(watermark, "2026-11-27T12:00:00Z")
        self.assertEqual(dates, ["2026-11-26", "2026-11-27"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["cost_amount"], "-0.50")
        self.assertEqual(mock_get.call_args_list[0].kwargs["headers"]["Authorization"], "Bearer export-secret")

        # Malformed dirty-dates raises EventsReportDownloaderError.
        bad_resp = MagicMock()
        bad_resp.raise_for_status.return_value = None
        bad_resp.json.return_value = {"watermark": "2026-11-27T00:00:00Z"}
        with patch.object(dl._session, "get", return_value=bad_resp):
            with self.assertRaises(EventsReportDownloaderError):
                dl.fetch_dirty_dates()

    def test_register_events_sync_beat(self):
        """Periodic sync_events_sources beat registers only when COST_EVENTS_URL is non-empty."""
        schedule = {}
        self.assertFalse(register_events_sync_beat(schedule, ""))
        self.assertNotIn(EVENTS_SYNC_BEAT_NAME, schedule)

        self.assertTrue(register_events_sync_beat(schedule, "http://cost-events:8020"))
        self.assertIn(EVENTS_SYNC_BEAT_NAME, schedule)
        self.assertEqual(schedule[EVENTS_SYNC_BEAT_NAME]["task"], "masu.celery.tasks.sync_events_sources")


class EventsIngestionPipelineTest(MasuTestCase):
    """End-to-end PostgreSQL tests for ingestion, UI summaries, tags, markup, and cleaner."""

    def setUp(self):
        super().setUp()
        self._created_providers = []

    def tearDown(self):
        with schema_context(self.schema):
            CostModelMap.objects.filter(cost_model__name__startswith="Events Test ").delete()
            CostModel.objects.filter(name__startswith="Events Test ").delete()
            TagMapping.objects.filter(child__provider_type=Provider.PROVIDER_EVENTS).delete()
            EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_EVENTS).delete()
            EventsTagsValues.objects.all().delete()
        for provider in self._created_providers:
            Sources.objects.filter(koku_uuid=provider.uuid).delete()
            CostUsageReportManifest.objects.filter(provider=provider).delete()
            if Provider.objects.filter(uuid=provider.uuid).exists():
                provider.delete()
        super().tearDown()

    def _make_events_provider(self, name="Test Events Source"):
        auth = ProviderAuthentication.objects.create(credentials={"token": "test-tok"})
        bs = ProviderBillingSource.objects.create(data_source={"url": "http://cost-events:8020"})
        provider = Provider(
            name=name,
            type=Provider.PROVIDER_EVENTS,
            authentication=auth,
            billing_source=bs,
            customer=self.customer,
            setup_complete=True,
            active=True,
        )
        super(Provider, provider).save()
        self._created_providers.append(provider)
        return provider

    @override_settings(ONPREM=True, COST_EVENTS_URL="http://cost-events.cost-mgmt.svc:8020")
    def test_ensure_builtin_events_source_idempotent(self):
        """ensure_builtin_events_source creates once and updates URL without duplicating."""
        ensured_1 = ensure_builtin_events_source()
        self.assertTrue(any(p.customer_id == self.customer.id for p in ensured_1))
        provider = Provider.objects.get(customer=self.customer, type=Provider.PROVIDER_EVENTS)
        self._created_providers.append(provider)
        self.assertEqual(provider.billing_source.data_source["url"], "http://cost-events.cost-mgmt.svc:8020")
        self.assertTrue(Sources.objects.filter(koku_uuid=provider.uuid).exists())

        with override_settings(COST_EVENTS_URL="https://cost-events.new.svc:8443"):
            ensure_builtin_events_source()
        self.assertEqual(Provider.objects.filter(customer=self.customer, type=Provider.PROVIDER_EVENTS).count(), 1)
        provider.refresh_from_db()
        self.assertEqual(provider.billing_source.data_source["url"], "https://cost-events.new.svc:8443")

    @override_settings(ONPREM=True, COST_EVENTS_URL="http://cost-events:8020")
    def test_full_sync_summaries_tag_mapping_markup_correction_and_cleaner(self):
        """Full lifecycle: pull sync, summaries, TagMapping, markup, correction, cleaner."""
        provider = self._make_events_provider()
        d1 = self.dh.this_month_start.date()
        d2 = d1.replace(day=min(d1.day + 1, 28))

        initial_rows = [
            {
                "usage_date": str(d1),
                "tenant_id": "tenant-acme",
                "tenant_name": "Acme Corp",
                "project_id": "proj-ai",
                "project_name": "AI Platform",
                "user_id": "alice",
                "service": "compute_instance",
                "meter": "compute",
                "catalog_item": "osac.vm.medium",
                "instance_type": "standard-4-8",
                "resource_id": "vm-1",
                "resource_name": "worker-1",
                "cluster_id": "cluster-prod-1",
                "deployment": "eu-central-1",
                "cost_type": "Infrastructure",
                "usage_amount": "100.000000",
                "unit": "seconds",
                "cost_amount": "10.000000000000000",
                "currency": "USD",
                "tags": {"cost_center": "cc-100", "env": "prod"},
                "entry_count": 5,
            },
            {
                "usage_date": str(d2),
                "tenant_id": "tenant-acme",
                "tenant_name": "Acme Corp",
                "project_id": None,
                "project_name": None,
                "user_id": None,
                "service": "custom_gpu_job",
                "meter": "gpu_seconds",
                "catalog_item": None,
                "instance_type": None,
                "resource_id": "job-42",
                "resource_name": None,
                "cluster_id": None,
                "deployment": None,
                "cost_type": "Supplementary",
                "usage_amount": "-20.000000",
                "unit": "seconds",
                "cost_amount": "-2.000000000000000",
                "currency": "USD",
                "tags": {"env": "prod"},
                "entry_count": 1,
            },
        ]

        # Pre-create a TagMapping: child "cost_center" -> parent "cost-center" for Events.
        with schema_context(self.schema):
            parent_key = EnabledTagKeys.objects.create(
                key="cost-center", enabled=True, provider_type=Provider.PROVIDER_EVENTS
            )
            child_key = EnabledTagKeys.objects.create(
                key="cost_center", enabled=True, provider_type=Provider.PROVIDER_EVENTS
            )
            TagMapping.objects.create(parent=parent_key, child=child_key)

            # Configure a 15% markup CostModel for this Events provider (Model A).
            cm = CostModel.objects.create(
                name="Events Test Markup 15%",
                description="15% markup",
                source_type=Provider.PROVIDER_EVENTS,
                markup={"value": "15", "unit": "percent"},
                rates=[],
            )
            CostModelMap.objects.create(cost_model=cm, provider_uuid=provider.uuid)

        mock_dl = MagicMock()
        mock_dl.fetch_dirty_dates.return_value = ("2026-11-27T10:00:00Z", [str(d1), str(d2)])
        mock_dl.fetch_daily_rollups.return_value = initial_rows

        result = EventsReportIngestor(provider, downloader=mock_dl).sync()
        self.assertFalse(result["skipped"])
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["watermark"], "2026-11-27T10:00:00Z")

        provider.refresh_from_db()
        self.assertEqual(provider.additional_context["events_watermark"], "2026-11-27T10:00:00Z")
        self.assertTrue(CostUsageReportManifest.objects.filter(provider=provider).exists())

        with schema_context(self.schema):
            # Verify daily summary rows, TagMapping rewrite, and 15% markup (including negative row).
            d1_row = EventsCostEntryLineItemDailySummary.objects.get(source_uuid=provider.uuid, usage_start=d1)
            self.assertEqual(d1_row.raw_cost, Decimal("10"))
            self.assertEqual(d1_row.markup_cost, Decimal("1.5"))
            self.assertEqual(d1_row.tags, {"cost-center": "cc-100", "env": "prod"})
            self.assertEqual(d1_row.user_id, "alice")

            d2_row = EventsCostEntryLineItemDailySummary.objects.get(source_uuid=provider.uuid, usage_start=d2)
            self.assertEqual(d2_row.raw_cost, Decimal("-2"))
            self.assertEqual(d2_row.markup_cost, Decimal("-0.3"))

            # Verify all 5 UI summary tables populated accurately.
            self.assertEqual(
                EventsCostSummaryP.objects.get(source_uuid=provider.uuid, usage_start=d1).markup_cost,
                Decimal("1.5"),
            )
            self.assertEqual(
                EventsCostSummaryByTenantP.objects.get(source_uuid=provider.uuid, usage_start=d1).tenant_name,
                "Acme Corp",
            )
            self.assertEqual(
                EventsCostSummaryByProjectP.objects.get(source_uuid=provider.uuid, usage_start=d1).project_id,
                "proj-ai",
            )
            self.assertEqual(
                EventsCostSummaryByServiceP.objects.get(source_uuid=provider.uuid, usage_start=d1).deployment,
                "eu-central-1",
            )
            meter_row = EventsUsageSummaryByMeterP.objects.get(source_uuid=provider.uuid, usage_start=d2)
            self.assertEqual(meter_row.meter, "gpu_seconds")
            self.assertEqual(meter_row.usage_amount, Decimal("-20"))

            # Verify EnabledTagKeys + EventsTagsSummary + EventsTagsValues populated (with mapped key).
            self.assertTrue(
                EnabledTagKeys.objects.filter(key="env", provider_type=Provider.PROVIDER_EVENTS, enabled=True).exists()
            )
            self.assertTrue(EventsTagsSummary.objects.filter(key="cost-center").exists())
            self.assertTrue(EventsTagsValues.objects.filter(key="cost-center", value="cc-100").exists())

            # Test updating CostModel markup to 20% via CostModelCostUpdater router.
            cm.markup = {"value": "20", "unit": "percent"}
            cm.save()

        CostModelCostUpdater(self.schema, provider.uuid).update_cost_model_costs(start_date=d1, end_date=d2)
        with schema_context(self.schema):
            self.assertEqual(
                EventsCostSummaryP.objects.get(source_uuid=provider.uuid, usage_start=d1).markup_cost,
                Decimal("2"),
            )
            self.assertEqual(
                EventsCostSummaryP.objects.get(source_uuid=provider.uuid, usage_start=d2).markup_cost,
                Decimal("-0.4"),
            )

        # Second incremental sync: d1 gets a full credit cancellation (0 rows returned for d1 -> old row deleted!).
        mock_dl2 = MagicMock()
        mock_dl2.fetch_dirty_dates.return_value = ("2026-11-27T11:00:00Z", [str(d1)])
        mock_dl2.fetch_daily_rollups.return_value = []
        EventsReportIngestor(provider, downloader=mock_dl2).sync()
        mock_dl2.fetch_dirty_dates.assert_called_once_with(since="2026-11-27T10:00:00Z", tenant_id=None)

        with schema_context(self.schema):
            self.assertFalse(
                EventsCostEntryLineItemDailySummary.objects.filter(source_uuid=provider.uuid, usage_start=d1).exists()
            )
            self.assertFalse(EventsCostSummaryP.objects.filter(source_uuid=provider.uuid, usage_start=d1).exists())
            # d2 remains untouched.
            self.assertTrue(
                EventsCostEntryLineItemDailySummary.objects.filter(source_uuid=provider.uuid, usage_start=d2).exists()
            )

        # Verify ExpiredDataRemover / EventsReportDBCleaner purges provider data via cascade_delete().
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_EVENTS)
        removed = remover.remove(simulate=False, provider_uuid=provider.uuid)
        self.assertGreaterEqual(len(removed), 1)
        with schema_context(self.schema):
            self.assertFalse(EventsCostEntryBill.objects.filter(provider_id=provider.uuid).exists())
            self.assertFalse(EventsCostEntryLineItemDailySummary.objects.filter(source_uuid=provider.uuid).exists())

        # Guard invalid cleaner argument combinations.
        with self.assertRaises(EventsReportDBCleanerError):
            EventsReportDBCleaner(self.schema).purge_expired_report_data()

    @override_settings(ONPREM=False, COST_EVENTS_URL="")
    @patch("masu.processor.is_feature_flag_enabled_by_schema", return_value=False)
    def test_sync_skips_when_events_flag_disabled(self, _mock_flag):
        """When EVENTS_SOURCE_FLAG is disabled on SaaS, sync skips without HTTP calls."""
        provider = self._make_events_provider(name="Disabled Events")
        mock_dl = MagicMock()
        result = EventsReportIngestor(provider, downloader=mock_dl).sync()
        self.assertTrue(result["skipped"])
        mock_dl.fetch_dirty_dates.assert_not_called()

    @override_settings(ONPREM=True, COST_EVENTS_URL="http://cost-events:8020")
    def test_cleaner_drops_expired_historical_partition(self):
        """purge_expired_report_data_by_date drops partitions on or before cutoff month."""
        provider = self._make_events_provider(name="Historical Events")
        old_date = date(2024, 1, 15)
        with EventsReportDBAccessor(self.schema) as accessor:
            accessor.replace_daily_summary_for_dates(
                provider_uuid=provider.uuid,
                dirty_dates=[old_date],
                rows=[
                    {
                        "usage_date": str(old_date),
                        "tenant_id": "t-old",
                        "service": "compute_instance",
                        "meter": "compute",
                        "cost_type": "Infrastructure",
                        "usage_amount": "10",
                        "unit": "seconds",
                        "cost_amount": "1.0",
                        "currency": "USD",
                        "tags": {},
                        "entry_count": 1,
                    }
                ],
            )

        cutoff = timezone.make_aware(datetime(2024, 2, 1))
        removed = EventsReportDBCleaner(self.schema).purge_expired_report_data(expired_date=cutoff, simulate=False)
        self.assertGreaterEqual(len(removed), 1)
        with schema_context(self.schema):
            self.assertFalse(
                EventsCostEntryLineItemDailySummary.objects.filter(
                    source_uuid=provider.uuid, usage_start=old_date
                ).exists()
            )
