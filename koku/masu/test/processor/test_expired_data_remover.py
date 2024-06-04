#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ExpiredDataRemover object."""
import logging
import re
from datetime import datetime
from unittest.mock import patch
from unittest.mock import PropertyMock
from uuid import uuid4

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.utils import timezone
from model_bakery import baker

from api.provider.models import Provider
from masu.config import Config
from masu.processor.expired_data_remover import ExpiredDataRemover
from masu.processor.expired_data_remover import ExpiredDataRemoverError
from masu.test import MasuTestCase
from reporting_common.models import CostUsageReportManifest


class ExpiredDataRemoverTest(MasuTestCase):
    """Test Cases for the ExpiredDataRemover object."""

    def test_initializer(self):
        """Test to init."""
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS)
        self.assertEqual(remover._months_to_keep, Config.MASU_RETAIN_NUM_MONTHS)
        self.assertEqual(remover._line_items_months, Config.MASU_RETAIN_NUM_MONTHS_LINE_ITEM_ONLY)
        remover2 = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS, 2, 2)
        self.assertEqual(remover2._months_to_keep, 2)
        self.assertEqual(remover2._line_items_months, 2)

    def test_initializer_ocp(self):
        """Test to init for OCP."""
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_OCP)
        self.assertEqual(remover._months_to_keep, Config.MASU_RETAIN_NUM_MONTHS)
        self.assertEqual(remover._line_items_months, Config.MASU_RETAIN_NUM_MONTHS_LINE_ITEM_ONLY)

    def test_initializer_azure(self):
        """Test to init for Azure."""
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AZURE)
        self.assertEqual(remover._months_to_keep, Config.MASU_RETAIN_NUM_MONTHS)
        self.assertEqual(remover._line_items_months, Config.MASU_RETAIN_NUM_MONTHS_LINE_ITEM_ONLY)

    def test_initializer_invalid_provider(self):
        """Test to init with unknown provider."""
        with self.assertRaises(ExpiredDataRemoverError):
            ExpiredDataRemover(self.schema, "BAD")

    @patch("masu.processor.aws.aws_report_db_cleaner.AWSReportDBCleaner.__init__", side_effect=Exception)
    def test_initializer_provider_exception(self, mock_aws_cleaner):
        """Test to init."""
        with self.assertRaises(ExpiredDataRemoverError):
            ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS)

    def test_calculate_expiration_date(self):
        """Test that the expiration date is correctly calculated."""
        date_matrix = [
            {
                "current_date": datetime(year=2018, month=7, day=1),
                "expected_expire": datetime(year=2018, month=7, day=1, tzinfo=settings.UTC)
                - relativedelta(months=Config.MASU_RETAIN_NUM_MONTHS),
                "months_to_keep": None,
            },
            {
                "current_date": datetime(year=2018, month=7, day=31),
                "expected_expire": datetime(year=2018, month=7, day=1, tzinfo=settings.UTC)
                - relativedelta(months=Config.MASU_RETAIN_NUM_MONTHS),
                "months_to_keep": None,
            },
            {
                "current_date": datetime(year=2018, month=3, day=20),
                "expected_expire": datetime(year=2018, month=3, day=1, tzinfo=settings.UTC)
                - relativedelta(months=Config.MASU_RETAIN_NUM_MONTHS),
                "months_to_keep": None,
            },
            {
                "current_date": datetime(year=2018, month=7, day=1),
                "expected_expire": datetime(year=2018, month=7, day=1, tzinfo=settings.UTC) - relativedelta(months=12),
                "months_to_keep": 12,
            },
            {
                "current_date": datetime(year=2018, month=7, day=31),
                "expected_expire": datetime(year=2018, month=7, day=1, tzinfo=settings.UTC) - relativedelta(months=12),
                "months_to_keep": 12,
            },
            {
                "current_date": datetime(year=2018, month=3, day=20),
                "expected_expire": datetime(year=2018, month=3, day=1, tzinfo=settings.UTC) - relativedelta(months=24),
                "months_to_keep": 24,
            },
        ]
        for test_case in date_matrix:
            with patch("masu.processor.expired_data_remover.DateHelper.today", new_callable=PropertyMock) as mock_dh:
                mock_dh.return_value = test_case.get("current_date")
                retention_policy = test_case.get("months_to_keep")
                if retention_policy:
                    remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS, retention_policy)
                else:
                    remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS)
                expire_date = remover._calculate_expiration_date()
                self.assertEqual(expire_date, test_case.get("expected_expire"))

    def test_remove(self):
        """Test that removes the expired data based on the retention policy."""
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS)
        removed_data = remover.remove()
        self.assertEqual(len(removed_data), 0)

    @patch("masu.processor.expired_data_remover.AWSReportDBCleaner.purge_expired_report_data")
    def test_remove_provider(self, mock_purge):
        """Test that remove is called with provider_uuid."""
        provider_uuid = self.aws_provider_uuid
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS)
        remover.remove(provider_uuid=provider_uuid)
        mock_purge.assert_called_with(simulate=False, provider_uuid=provider_uuid)

    def test_delete_expired_cost_usage_report_manifest(self):
        """
        Test that expired CostUsageReportManifests are removed.

        This test inserts CostUsageReportManifest objects,
        And then deletes CostUsageReportManifest objects older than
        the calculated expiration_date.
        """

        provider_type_dict = {
            Provider.PROVIDER_AWS_LOCAL: self.aws_provider_uuid,
            Provider.PROVIDER_AZURE_LOCAL: self.azure_provider_uuid,
            Provider.PROVIDER_OCP: self.ocp_provider_uuid,
        }
        for provider_type in provider_type_dict:
            remover = ExpiredDataRemover(self.schema, provider_type)
            expiration_date = remover._calculate_expiration_date()
            current_month = datetime.today().replace(day=1)
            day_before_cutoff = expiration_date - relativedelta(days=1)
            dates = [current_month, day_before_cutoff, expiration_date]
            uuids = []
            uuids_to_be_deleted = []
            for date in dates:
                creation_datetime = current_month
                uuid = uuid4()
                data = {
                    "assembly_id": uuid,
                    "creation_datetime": creation_datetime,
                    "billing_period_start_datetime": date,
                    "num_total_files": 1,
                    "provider_id": provider_type_dict[provider_type],
                }
                uuids.append(uuid)
                if date == day_before_cutoff:
                    uuids_to_be_deleted.append(uuid)
                manifest_entry = CostUsageReportManifest(**data)
                manifest_entry.save()

            remover.remove()
            for uuid in uuids:
                record_count = CostUsageReportManifest.objects.filter(assembly_id=uuid).count()
                if uuid in uuids_to_be_deleted:
                    self.assertEqual(0, record_count)
                else:
                    self.assertEqual(1, record_count)

    def test_simulate_delete_expired_cost_usage_report_manifest(self):
        """
        Test that expired CostUsageReportManifest is not removed during simulation.

        Test that the number of records that would have been deleted is logged.
        """

        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS)
        expiration_date = remover._calculate_expiration_date()
        day_before_cutoff = expiration_date - relativedelta(days=1)
        day_before_cutoff_data = {
            "assembly_id": uuid4(),
            "creation_datetime": None,
            "billing_period_start_datetime": day_before_cutoff,
            "num_total_files": 1,
            "provider_id": self.aws_provider_uuid,
        }
        CostUsageReportManifest(**day_before_cutoff_data).save()
        with self.assertLogs(logger="masu.processor.expired_data_remover", level="INFO") as cm:
            logging.disable(logging.NOTSET)
            remover.remove(simulate=True)
            expected_log_message = "Removed CostUsageReportManifest"
            # Check if the log message exists in the log output:
            self.assertTrue(
                any(match is not None for match in [re.search(expected_log_message, line) for line in cm.output]),
                "Expected to see log message: "
                + expected_log_message
                + "in the list of log messages"
                + " but the list of log messages was instead : "
                + str(cm.output),
            )
        # Re-enable log suppression
        logging.disable(logging.CRITICAL)

    def test_remove_cost_usage_manifests_by_provider_uuid(self):
        """
        Test that calling remove(provider_uuid) deletes CostUsageReportManifests.

        CostUsageReportManifests that are associated with the provider_uuid
        should be deleted.
        """
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS_LOCAL)
        expiration_date = remover._calculate_expiration_date()
        current_month = datetime.today().replace(day=1)
        day_before_cutoff = expiration_date - relativedelta(days=1)
        fixture_records = [
            (self.aws_provider_uuid, expiration_date),  # not expired, should not delete
            (self.aws_provider_uuid, day_before_cutoff),  # expired, should delete
            (self.azure_provider_uuid, day_before_cutoff),  # expired, should not delete
        ]
        manifest_uuids = []
        manifest_uuids_to_be_deleted = []
        creation_datetime = current_month
        for fixture_record in fixture_records:
            manifest_uuid = uuid4()
            data = {
                "assembly_id": manifest_uuid,
                "creation_datetime": creation_datetime,
                "billing_period_start_datetime": fixture_record[1],
                "num_total_files": 1,
                "provider_id": fixture_record[0],
            }
            CostUsageReportManifest(**data).save()
            manifest_uuids.append(manifest_uuid)
            if fixture_record[1] == day_before_cutoff and fixture_record[0] == self.aws_provider_uuid:
                manifest_uuids_to_be_deleted.append(manifest_uuid)
        remover.remove(provider_uuid=self.aws_provider_uuid)

        for manifest_uuid in manifest_uuids:
            record_count = CostUsageReportManifest.objects.filter(assembly_id=manifest_uuid).count()
            if manifest_uuid in manifest_uuids_to_be_deleted:
                self.assertEqual(0, record_count)
            else:
                self.assertEqual(1, record_count)

    def test_simulate_delete_expired_cost_usage_report_manifest_by_provider_uuid(self):
        """
        Test simulating the deletion of expired CostUsageReportManifests.

        using remove(provider_uuid)
        """
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS)
        expiration_date = remover._calculate_expiration_date()
        day_before_cutoff = expiration_date - relativedelta(days=1)
        manifest_id = 7766
        day_before_cutoff_data = {
            "id": manifest_id,
            "assembly_id": uuid4(),
            "creation_datetime": None,
            "billing_period_start_datetime": day_before_cutoff,
            "num_total_files": 1,
            "provider_id": self.aws_provider_uuid,
        }
        manifest_entry = CostUsageReportManifest(**day_before_cutoff_data)
        manifest_entry.save()

        baker.make(
            "CostUsageReportStatus",
            _quantity=manifest_entry.num_total_files,
            manifest_id=manifest_id,
            completed_datetime=timezone.now(),
        )

        count_records = CostUsageReportManifest.objects.count()
        with self.assertLogs(logger="masu.processor.expired_data_remover", level="INFO") as cm:
            logging.disable(logging.NOTSET)
            remover.remove(simulate=True, provider_uuid=self.aws_provider_uuid)
            expected_log_message = "Removed CostUsageReportManifest"
            # Check if the log message exists in the log output:
            self.assertTrue(
                any(match is not None for match in [re.search(expected_log_message, line) for line in cm.output]),
                "Expected to see log message: "
                + expected_log_message
                + "in the list of log messages"
                + " but the list of log messages was instead : "
                + str(cm.output),
            )
        # Re-enable log suppression
        logging.disable(logging.CRITICAL)

        self.assertEqual(count_records, CostUsageReportManifest.objects.count())
