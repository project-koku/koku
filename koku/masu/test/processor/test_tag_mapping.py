#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for shared tag-mapping apply."""
from datetime import date
from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

from django.conf import settings
from django.utils import timezone
from django_tenants.utils import schema_context

from api.provider.models import Provider
from api.provider.models import ProviderInfrastructureMap
from api.utils import to_date
from common.queues import SummaryQueue
from koku.cache import TAG_MAPPING_PREFIX
from masu.database import AWS_CUR_TABLE_MAP
from masu.processor.tag_mapping import apply_tag_mappings
from masu.processor.tag_mapping import ROW_SCOPE_ALL
from masu.processor.tag_mapping import ROW_SCOPE_INFRA
from masu.processor.tag_mapping import ROW_SCOPE_USAGE
from masu.processor.tasks import apply_tag_mappings as apply_tag_mappings_task
from masu.processor.tasks import delayed_apply_tag_mappings
from masu.test import MasuTestCase
from masu.util.common import SummaryRangeConfig
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import VM_UI_SUMMARY_TABLE
from reporting_common.models import DelayedCeleryTasks


class ApplyTagMappingsTest(MasuTestCase):
    """Tests for masu.processor.tag_mapping.apply_tag_mappings."""

    def setUp(self):
        super().setUp()
        self.start = self.dh.this_month_start.date()
        self.end = self.dh.today.date()

    def _mock_accessor(self, mock_cls, report_period_id=7, bill_ids=None):
        mock_acc = MagicMock()
        mock_acc.schema = self.schema
        mock_acc.report_periods_for_provider_uuid.return_value = Mock(id=report_period_id)
        if bill_ids is None:
            bill_ids = [11]
        bills = [Mock(id=bill_id) for bill_id in bill_ids]
        mock_acc.bills_for_provider_uuid.return_value = bills
        mock_cls.return_value = mock_acc
        mock_acc.__enter__.return_value = mock_acc
        return mock_acc

    @patch("masu.processor.tag_mapping.OCPReportDBAccessor")
    def test_ocp_usage_scope_maps_usage_then_label_summaries(self, mock_ocp_cls):
        mock_acc = self._mock_accessor(mock_ocp_cls)
        apply_tag_mappings(
            self.schema,
            self.ocp_provider,
            self.start,
            self.end,
            row_scope=ROW_SCOPE_USAGE,
        )

        mock_acc.update_line_item_daily_summary_with_tag_mapping.assert_called_once_with(
            self.start, self.end, [7], infrastructure_only=False
        )
        mock_acc.populate_pod_label_summary_table.assert_called_once_with([7], self.start, self.end)
        mock_acc.populate_volume_label_summary_table.assert_called_once_with([7], self.start, self.end)
        mock_acc.populate_ui_summary_tables.assert_called_once_with(
            SummaryRangeConfig(start_date=self.start, end_date=self.end),
            self.ocp_provider.uuid,
            tables=(VM_UI_SUMMARY_TABLE,),
        )

    @patch("masu.processor.tag_mapping.OCPReportDBAccessor")
    def test_ocp_infra_scope_maps_infra_only(self, mock_ocp_cls):
        mock_acc = self._mock_accessor(mock_ocp_cls)
        apply_tag_mappings(
            self.schema,
            self.ocp_provider,
            self.start,
            self.end,
            row_scope=ROW_SCOPE_INFRA,
        )

        mock_acc.update_line_item_daily_summary_with_tag_mapping.assert_called_once_with(
            self.start, self.end, [7], infrastructure_only=True
        )
        mock_acc.populate_pod_label_summary_table.assert_not_called()
        mock_acc.populate_volume_label_summary_table.assert_not_called()
        mock_acc.populate_ui_summary_tables.assert_not_called()

    @patch("masu.processor.tag_mapping.AWSReportDBAccessor")
    @patch("masu.processor.tag_mapping.OCPReportDBAccessor")
    def test_ocp_all_with_linked_cloud_maps_ocp_on_cloud(self, mock_ocp_cls, mock_aws_cls):
        mock_ocp = self._mock_accessor(mock_ocp_cls)
        mock_aws = self._mock_accessor(mock_aws_cls, bill_ids=[22])
        infra_map = ProviderInfrastructureMap.objects.create(
            infrastructure_type=Provider.PROVIDER_AWS,
            infrastructure_provider=self.aws_provider,
        )
        self.ocp_provider.infrastructure = infra_map
        self.ocp_provider.save()
        self.ocp_provider.refresh_from_db()

        apply_tag_mappings(
            self.schema,
            self.ocp_provider,
            self.start,
            self.end,
            row_scope=ROW_SCOPE_ALL,
            include_linked_ocp_on_cloud=True,
        )

        (
            usage_call,
            infra_call,
        ) = mock_ocp.update_line_item_daily_summary_with_tag_mapping.call_args_list
        self.assertEqual(usage_call.kwargs["infrastructure_only"], False)
        self.assertEqual(infra_call.kwargs["infrastructure_only"], True)
        mock_aws.populate_ocp_on_aws_tag_information.assert_called_once_with(["22"], self.start, self.end, 7)

    @patch(
        "masu.processor.tag_mapping.is_feature_cost_4403_ec2_compute_cost_enabled",
        return_value=True,
    )
    @patch("masu.processor.tag_mapping.AWSReportDBAccessor")
    def test_aws_maps_daily_then_ec2_then_tags_summary(self, mock_aws_cls, _mock_ec2_flag):
        mock_acc = self._mock_accessor(mock_aws_cls, bill_ids=[5])
        apply_tag_mappings(self.schema, self.aws_provider, self.start, self.end)

        mock_acc.update_line_item_daily_summary_with_tag_mapping.assert_any_call(self.start, self.end, ["5"])
        mock_acc.update_line_item_daily_summary_with_tag_mapping.assert_any_call(
            self.start.replace(day=1),
            self.end,
            ["5"],
            table_name=AWS_CUR_TABLE_MAP["ec2_compute_summary"],
        )
        mock_acc.populate_tags_summary_table.assert_called_once_with(["5"], self.start, self.end)

    @patch("masu.processor.tag_mapping.OCPReportDBAccessor")
    def test_skips_when_no_report_period(self, mock_ocp_cls):
        mock_acc = MagicMock()
        mock_acc.report_periods_for_provider_uuid.return_value = None
        mock_ocp_cls.return_value = mock_acc
        mock_acc.__enter__.return_value = mock_acc

        apply_tag_mappings(
            self.schema,
            self.ocp_provider,
            self.start,
            self.end,
            row_scope=ROW_SCOPE_USAGE,
        )

        mock_acc.update_line_item_daily_summary_with_tag_mapping.assert_not_called()

    @patch("masu.processor.tag_mapping.OCPReportDBAccessor")
    def test_ocp_coerces_datetime_strings_for_summary_range(self, mock_ocp_cls):
        mock_acc = self._mock_accessor(mock_ocp_cls)
        start = "2026-10-01 00:00:00+00:00"
        end = "2026-10-12 00:00:00+00:00"

        apply_tag_mappings(
            self.schema,
            self.ocp_provider,
            start,
            end,
            row_scope=ROW_SCOPE_USAGE,
        )

        expected_start = date(2026, 10, 1)
        expected_end = date(2026, 10, 12)
        mock_acc.update_line_item_daily_summary_with_tag_mapping.assert_called_once_with(
            expected_start, expected_end, [7], infrastructure_only=False
        )
        summary_range = mock_acc.populate_ui_summary_tables.call_args.args[0]
        self.assertEqual(summary_range.start_date, expected_start)
        self.assertEqual(summary_range.end_date, expected_end)

    @patch("masu.processor.tag_mapping.AzureReportDBAccessor")
    def test_azure_maps_daily_then_tags_summary(self, mock_azure_cls):
        mock_acc = self._mock_accessor(mock_azure_cls, bill_ids=[3])
        apply_tag_mappings(self.schema, self.azure_provider, self.start, self.end)
        mock_acc.update_line_item_daily_summary_with_tag_mapping.assert_called_once_with(self.start, self.end, ["3"])
        mock_acc.populate_tags_summary_table.assert_called_once_with(["3"], self.start, self.end)

    @patch("masu.processor.tag_mapping.GCPReportDBAccessor")
    def test_gcp_maps_daily_then_tags_summary(self, mock_gcp_cls):
        mock_acc = self._mock_accessor(mock_gcp_cls, bill_ids=[4])
        apply_tag_mappings(self.schema, self.gcp_provider, self.start, self.end)
        mock_acc.update_line_item_daily_summary_with_tag_mapping.assert_called_once_with(self.start, self.end, ["4"])
        mock_acc.populate_tags_summary_table.assert_called_once_with(["4"], self.start, self.end)

    @patch(
        "masu.processor.tag_mapping.is_feature_cost_4403_ec2_compute_cost_enabled",
        return_value=False,
    )
    @patch("masu.processor.tag_mapping.AWSReportDBAccessor")
    def test_aws_skips_ec2_when_flag_off(self, mock_aws_cls, _mock_ec2_flag):
        mock_acc = self._mock_accessor(mock_aws_cls, bill_ids=[5])
        apply_tag_mappings(self.schema, self.aws_provider, self.start, self.end)
        mock_acc.update_line_item_daily_summary_with_tag_mapping.assert_called_once_with(self.start, self.end, ["5"])
        mock_acc.populate_tags_summary_table.assert_called_once_with(["5"], self.start, self.end)

    def test_skips_unsupported_provider_type(self):
        provider = Mock(uuid="11111111-1111-1111-1111-111111111111", type="Bogus")
        with (
            patch("masu.processor.tag_mapping.AWSReportDBAccessor") as mock_aws,
            patch("masu.processor.tag_mapping.OCPReportDBAccessor") as mock_ocp,
        ):
            apply_tag_mappings(self.schema, provider, self.start, self.end)
        mock_aws.assert_not_called()
        mock_ocp.assert_not_called()

    @patch("masu.processor.tag_mapping.AWSReportDBAccessor")
    @patch("masu.processor.tag_mapping.OCPReportDBAccessor")
    def test_ocp_linked_cloud_skipped_without_infrastructure(self, mock_ocp_cls, mock_aws_cls):
        self._mock_accessor(mock_ocp_cls)
        apply_tag_mappings(
            self.schema,
            self.ocp_provider,
            self.start,
            self.end,
            row_scope=ROW_SCOPE_USAGE,
            include_linked_ocp_on_cloud=True,
        )
        mock_aws_cls.assert_not_called()

    @patch("masu.processor.tag_mapping.AWSReportDBAccessor")
    @patch("masu.processor.tag_mapping.OCPReportDBAccessor")
    def test_cloud_include_linked_maps_ocp_on_cloud_clusters(self, mock_ocp_cls, mock_aws_cls):
        self._mock_accessor(mock_ocp_cls)
        mock_aws = self._mock_accessor(mock_aws_cls, bill_ids=[9])
        apply_tag_mappings(
            self.schema,
            self.aws_provider,
            self.start,
            self.end,
            include_linked_ocp_on_cloud=True,
        )
        mock_aws.populate_ocp_on_aws_tag_information.assert_called()
        mock_aws.populate_tags_summary_table.assert_called_once_with(["9"], self.start, self.end)

    @patch("masu.processor.tag_mapping.AzureReportDBAccessor")
    @patch("masu.processor.tag_mapping.OCPReportDBAccessor")
    def test_ocp_on_azure_maps_project_tables(self, mock_ocp_cls, mock_azure_cls):
        self._mock_accessor(mock_ocp_cls)
        mock_azure = self._mock_accessor(mock_azure_cls, bill_ids=[8])
        apply_tag_mappings(
            self.schema,
            self.ocp_on_azure_ocp_provider,
            self.start,
            self.end,
            row_scope=ROW_SCOPE_USAGE,
            include_linked_ocp_on_cloud=True,
        )
        mock_azure.populate_ocp_on_azure_tag_information.assert_called_once_with(["8"], self.start, self.end, 7)

    @patch("masu.processor.tag_mapping.GCPReportDBAccessor")
    @patch("masu.processor.tag_mapping.OCPReportDBAccessor")
    def test_ocp_on_gcp_maps_project_tables(self, mock_ocp_cls, mock_gcp_cls):
        self._mock_accessor(mock_ocp_cls)
        mock_gcp = self._mock_accessor(mock_gcp_cls, bill_ids=[6])
        apply_tag_mappings(
            self.schema,
            self.ocp_on_gcp_ocp_provider,
            self.start,
            self.end,
            row_scope=ROW_SCOPE_USAGE,
            include_linked_ocp_on_cloud=True,
        )
        mock_gcp.populate_ocp_on_gcp_tag_information.assert_called_once_with(["6"], self.start, self.end, 7)

    @patch("masu.processor.tag_mapping.AWSReportDBAccessor")
    @patch("masu.processor.tag_mapping.OCPReportDBAccessor")
    def test_ocp_on_cloud_skips_when_no_bills(self, mock_ocp_cls, mock_aws_cls):
        self._mock_accessor(mock_ocp_cls)
        mock_aws = self._mock_accessor(mock_aws_cls, bill_ids=[])
        apply_tag_mappings(
            self.schema,
            self.ocp_on_aws_ocp_provider,
            self.start,
            self.end,
            row_scope=ROW_SCOPE_USAGE,
            include_linked_ocp_on_cloud=True,
        )
        mock_aws.populate_ocp_on_aws_tag_information.assert_not_called()

    @patch("masu.processor.tag_mapping.AzureReportDBAccessor")
    @patch("masu.processor.tag_mapping.OCPReportDBAccessor")
    def test_ocp_on_azure_skips_when_no_bills(self, mock_ocp_cls, mock_azure_cls):
        self._mock_accessor(mock_ocp_cls)
        mock_azure = self._mock_accessor(mock_azure_cls, bill_ids=[])
        apply_tag_mappings(
            self.schema,
            self.ocp_on_azure_ocp_provider,
            self.start,
            self.end,
            row_scope=ROW_SCOPE_USAGE,
            include_linked_ocp_on_cloud=True,
        )
        mock_azure.populate_ocp_on_azure_tag_information.assert_not_called()

    @patch("masu.processor.tag_mapping.GCPReportDBAccessor")
    @patch("masu.processor.tag_mapping.OCPReportDBAccessor")
    def test_ocp_on_gcp_skips_when_no_bills(self, mock_ocp_cls, mock_gcp_cls):
        self._mock_accessor(mock_ocp_cls)
        mock_gcp = self._mock_accessor(mock_gcp_cls, bill_ids=[])
        apply_tag_mappings(
            self.schema,
            self.ocp_on_gcp_ocp_provider,
            self.start,
            self.end,
            row_scope=ROW_SCOPE_USAGE,
            include_linked_ocp_on_cloud=True,
        )
        mock_gcp.populate_ocp_on_gcp_tag_information.assert_not_called()

    @patch("masu.processor.tag_mapping.AzureReportDBAccessor")
    @patch("masu.processor.tag_mapping.OCPReportDBAccessor")
    def test_azure_cloud_include_linked_maps_ocp_on_azure(self, mock_ocp_cls, mock_azure_cls):
        self._mock_accessor(mock_ocp_cls)
        mock_azure = self._mock_accessor(mock_azure_cls, bill_ids=[8])
        apply_tag_mappings(
            self.schema,
            self.azure_provider,
            self.start,
            self.end,
            include_linked_ocp_on_cloud=True,
        )
        mock_azure.populate_ocp_on_azure_tag_information.assert_called()
        mock_azure.populate_tags_summary_table.assert_called_once_with(["8"], self.start, self.end)

    @patch("masu.processor.tag_mapping.GCPReportDBAccessor")
    @patch("masu.processor.tag_mapping.OCPReportDBAccessor")
    def test_gcp_cloud_include_linked_maps_ocp_on_gcp(self, mock_ocp_cls, mock_gcp_cls):
        self._mock_accessor(mock_ocp_cls)
        mock_gcp = self._mock_accessor(mock_gcp_cls, bill_ids=[6])
        apply_tag_mappings(
            self.schema,
            self.gcp_provider,
            self.start,
            self.end,
            include_linked_ocp_on_cloud=True,
        )
        mock_gcp.populate_ocp_on_gcp_tag_information.assert_called()
        mock_gcp.populate_tags_summary_table.assert_called_once_with(["6"], self.start, self.end)

    @patch("masu.processor.tag_mapping.AWSReportDBAccessor")
    @patch("masu.processor.tag_mapping.OCPReportDBAccessor")
    def test_ocp_on_cloud_skips_when_no_report_period(self, mock_ocp_cls, mock_aws_cls):
        mock_ocp = MagicMock()
        mock_ocp.report_periods_for_provider_uuid.return_value = None
        mock_ocp_cls.return_value = mock_ocp
        apply_tag_mappings(
            self.schema,
            self.ocp_on_aws_ocp_provider,
            self.start,
            self.end,
            row_scope=ROW_SCOPE_USAGE,
            include_linked_ocp_on_cloud=True,
        )
        mock_aws_cls.assert_not_called()


class ApplyTagMappingsTaskTest(MasuTestCase):
    """Tests for the apply_tag_mappings Celery task."""

    @patch("masu.processor.tasks.is_source_disabled", return_value=False)
    @patch("masu.processor.tasks.is_summary_processing_disabled", return_value=False)
    @patch("masu.processor.tag_mapping.apply_tag_mappings")
    def test_task_applies_mappings_for_provider(self, mock_apply, _mock_summary, _mock_source):
        start = self.dh.this_month_start
        end = self.dh.today
        apply_tag_mappings_task(
            self.schema,
            str(self.ocp_provider.uuid),
            str(start),
            str(end),
            synchronous=True,
        )
        mock_apply.assert_called_once()
        args, kwargs = mock_apply.call_args
        self.assertEqual(args[0], self.schema)
        self.assertEqual(str(args[1].uuid), str(self.ocp_provider.uuid))
        self.assertEqual(args[2], to_date(start))
        self.assertEqual(args[3], to_date(end))
        self.assertTrue(kwargs["include_linked_ocp_on_cloud"])

    @patch("masu.processor.tasks.is_source_disabled", return_value=False)
    @patch("masu.processor.tasks.is_summary_processing_disabled", return_value=False)
    @patch("masu.processor.tag_mapping.apply_tag_mappings")
    def test_task_bumps_data_updated_timestamp(self, mock_apply, _mock_summary, _mock_source):
        before = timezone.now() - timedelta(hours=1)
        Provider.objects.filter(pk=self.ocp_provider.pk).update(data_updated_timestamp=before)

        apply_tag_mappings_task(
            self.schema,
            str(self.ocp_provider.uuid),
            str(self.dh.this_month_start),
            str(self.dh.today),
            synchronous=True,
        )

        self.ocp_provider.refresh_from_db()
        self.assertGreater(self.ocp_provider.data_updated_timestamp, before)
        mock_apply.assert_called_once()

    @patch("masu.processor.tasks.is_source_disabled", return_value=False)
    @patch("masu.processor.tasks.is_summary_processing_disabled", return_value=False)
    @patch("masu.processor.tag_mapping.apply_tag_mappings")
    def test_task_bumps_linked_cloud_and_ocp_on_cloud(self, mock_apply, _mock_summary, _mock_source):
        ocp = self.ocp_on_aws_ocp_provider
        aws = Provider.objects.get(uuid=ocp.infrastructure.infrastructure_provider_id)
        before = timezone.now() - timedelta(hours=1)
        Provider.objects.filter(uuid__in=[ocp.uuid, aws.uuid]).update(data_updated_timestamp=before)
        with schema_context(self.schema):
            OCPUsageReportPeriod.objects.filter(provider_id=ocp.uuid).update(ocp_on_cloud_updated_datetime=before)

        apply_tag_mappings_task(
            self.schema,
            str(ocp.uuid),
            str(self.dh.this_month_start),
            str(self.dh.today),
            synchronous=True,
        )

        ocp.refresh_from_db()
        aws.refresh_from_db()
        self.assertGreater(ocp.data_updated_timestamp, before)
        self.assertGreater(aws.data_updated_timestamp, before)
        with schema_context(self.schema):
            rp = OCPUsageReportPeriod.objects.filter(
                provider_id=ocp.uuid,
                report_period_start__year=self.dh.this_month_start.year,
                report_period_start__month=self.dh.this_month_start.month,
            ).first()
            self.assertIsNotNone(rp)
            self.assertGreater(rp.ocp_on_cloud_updated_datetime, before)
            self.assertGreater(ocp.data_updated_timestamp, rp.ocp_on_cloud_updated_datetime)
        mock_apply.assert_called_once()

    @patch("masu.processor.tasks.is_source_disabled", return_value=False)
    @patch("masu.processor.tasks.is_summary_processing_disabled", return_value=False)
    @patch("masu.processor.tag_mapping.apply_tag_mappings")
    def test_task_skips_missing_provider(self, mock_apply, _mock_summary, _mock_source):
        apply_tag_mappings_task(
            self.schema,
            "00000000-0000-0000-0000-000000000000",
            str(self.dh.this_month_start),
            synchronous=True,
        )
        mock_apply.assert_not_called()

    @patch("masu.processor.tasks.invalidate_view_cache_for_tenant_and_source_type")
    @patch("masu.processor.tasks.invalidate_cache_for_tenant_and_cache_key")
    @patch("masu.processor.tasks.is_source_disabled", return_value=False)
    @patch("masu.processor.tasks.is_summary_processing_disabled", return_value=False)
    @patch("masu.processor.tag_mapping.apply_tag_mappings")
    def test_task_invalidates_report_cache(
        self, mock_apply, _mock_summary, _mock_source, mock_tag_cache, mock_view_cache
    ):
        apply_tag_mappings_task(
            self.schema,
            str(self.ocp_provider.uuid),
            str(self.dh.this_month_start),
            str(self.dh.today),
            synchronous=True,
        )
        called_types = {call.args[1] for call in mock_view_cache.call_args_list}
        self.assertIn(Provider.PROVIDER_OCP, called_types)
        for call in mock_view_cache.call_args_list:
            self.assertEqual(call.args[0], self.schema)
        mock_tag_cache.assert_called_once_with(self.schema, TAG_MAPPING_PREFIX)
        mock_apply.assert_called_once()

    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=False)
    @patch("masu.processor.tasks.get_customer_queue", return_value=SummaryQueue.DEFAULT)
    def test_delayed_apply_stores_iso_dates(self, _mock_queue, _mock_delay):
        delayed_apply_tag_mappings(self.schema, [self.ocp_provider.uuid])
        row = DelayedCeleryTasks.objects.get(provider_uuid=self.ocp_provider.uuid)
        self.assertEqual(row.task_kwargs["start_date"], str(to_date(self.dh.this_month_start)))
        self.assertEqual(row.task_kwargs["end_date"], str(to_date(self.dh.today)))
        self.assertNotIn(" ", row.task_kwargs["start_date"])
        self.assertNotIn(" ", row.task_kwargs["end_date"])

    @patch("masu.processor.tasks.is_source_disabled", return_value=False)
    @patch("masu.processor.tasks.is_summary_processing_disabled", return_value=True)
    @patch("masu.processor.tag_mapping.apply_tag_mappings")
    def test_task_skips_when_summary_processing_disabled(self, mock_apply, _mock_summary, _mock_source):
        apply_tag_mappings_task(
            self.schema,
            str(self.ocp_provider.uuid),
            str(self.dh.this_month_start),
            synchronous=True,
        )
        mock_apply.assert_not_called()

    @patch("masu.processor.tasks.is_source_disabled", return_value=True)
    @patch("masu.processor.tasks.is_summary_processing_disabled", return_value=False)
    @patch("masu.processor.tag_mapping.apply_tag_mappings")
    def test_task_skips_when_source_disabled(self, mock_apply, _mock_summary, _mock_source):
        apply_tag_mappings_task(
            self.schema,
            str(self.ocp_provider.uuid),
            str(self.dh.this_month_start),
            synchronous=True,
        )
        mock_apply.assert_not_called()

    @patch("masu.processor.tasks.is_source_disabled", return_value=False)
    @patch("masu.processor.tasks.is_summary_processing_disabled", return_value=False)
    @patch("masu.processor.tag_mapping.apply_tag_mappings")
    @patch("masu.processor.tasks.apply_tag_mappings.s")
    @patch("masu.processor.tasks.WorkerCache")
    def test_task_requeues_when_already_running(
        self, mock_cache_cls, mock_signature, mock_apply, _mock_summary, _mock_source
    ):
        mock_cache_cls.return_value.single_task_is_running.return_value = True
        apply_tag_mappings_task(
            self.schema,
            str(self.ocp_provider.uuid),
            str(self.dh.this_month_start),
            str(self.dh.today),
            synchronous=False,
        )
        mock_signature.return_value.apply_async.assert_called_once()
        mock_apply.assert_not_called()

    @patch("reporting_common.models.celery_app")
    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=True)
    @patch("masu.processor.tasks.get_customer_queue", return_value=SummaryQueue.DEFAULT)
    def test_delayed_apply_bypasses_when_flag_enabled(self, _mock_queue, _mock_delay, mock_celery_app):
        mock_celery_app.send_task.return_value = Mock(id="mocked_result_id")
        delayed_apply_tag_mappings(self.schema, [self.ocp_provider.uuid])
        self.assertFalse(DelayedCeleryTasks.objects.filter(provider_uuid=self.ocp_provider.uuid).exists())
        mock_celery_app.send_task.assert_called_once()

    @patch("masu.processor.tasks.is_source_disabled", return_value=False)
    @patch("masu.processor.tasks.is_summary_processing_disabled", return_value=False)
    @patch("masu.processor.tag_mapping.apply_tag_mappings")
    def test_task_bumps_linked_ocp_when_started_from_cloud(self, mock_apply, _mock_summary, _mock_source):
        ocp = self.ocp_on_aws_ocp_provider
        aws = Provider.objects.get(uuid=ocp.infrastructure.infrastructure_provider_id)
        before = timezone.now() - timedelta(hours=1)
        Provider.objects.filter(uuid__in=[ocp.uuid, aws.uuid]).update(data_updated_timestamp=before)

        apply_tag_mappings_task(
            self.schema,
            str(aws.uuid),
            str(self.dh.this_month_start),
            str(self.dh.today),
            synchronous=True,
        )

        ocp.refresh_from_db()
        aws.refresh_from_db()
        self.assertGreater(ocp.data_updated_timestamp, before)
        self.assertGreater(aws.data_updated_timestamp, before)
        mock_apply.assert_called_once()

    @patch("masu.processor.tasks.is_source_disabled", return_value=False)
    @patch("masu.processor.tasks.is_summary_processing_disabled", return_value=False)
    @patch("masu.processor.tag_mapping.apply_tag_mappings")
    @patch("masu.processor.tasks.WorkerCache")
    def test_task_locks_and_releases_worker_cache(self, mock_cache_cls, mock_apply, _mock_summary, _mock_source):
        mock_cache = mock_cache_cls.return_value
        mock_cache.single_task_is_running.return_value = False
        apply_tag_mappings_task(
            self.schema,
            str(self.ocp_provider.uuid),
            str(self.dh.this_month_start),
            str(self.dh.today),
            synchronous=False,
        )
        mock_cache.lock_single_task.assert_called_once()
        mock_cache.release_single_task.assert_called_once()
        mock_apply.assert_called_once()

    @patch("masu.processor.tasks.is_source_disabled", return_value=False)
    @patch("masu.processor.tasks.is_summary_processing_disabled", return_value=False)
    @patch("masu.processor.tag_mapping.apply_tag_mappings")
    @patch("masu.processor.tasks.get_customer_queue", return_value=SummaryQueue.XL)
    @patch("masu.processor.tasks.WorkerCache")
    def test_task_uses_large_customer_lock_timeout(
        self, mock_cache_cls, _mock_queue, mock_apply, _mock_summary, _mock_source
    ):
        mock_cache = mock_cache_cls.return_value
        mock_cache.single_task_is_running.return_value = False
        apply_tag_mappings_task(
            self.schema,
            str(self.ocp_provider.uuid),
            str(self.dh.this_month_start),
            str(self.dh.today),
            synchronous=False,
        )
        timeout = mock_cache.lock_single_task.call_args.kwargs["timeout"]
        self.assertEqual(timeout, settings.WORKER_CACHE_LARGE_CUSTOMER_TIMEOUT)
        mock_apply.assert_called_once()
