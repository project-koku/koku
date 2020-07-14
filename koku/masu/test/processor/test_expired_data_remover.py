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
"""Test the ExpiredDataRemover object."""
import logging
import re
from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

import pytz
from dateutil import relativedelta

from api.provider.models import Provider
from masu.external.date_accessor import DateAccessor
from masu.processor.expired_data_remover import ExpiredDataRemover
from masu.processor.expired_data_remover import ExpiredDataRemoverError
from masu.test import MasuTestCase
from masu.test.database.helpers import ManifestCreationHelper
from reporting_common.models import CostUsageReportManifest


class ExpiredDataRemoverTest(MasuTestCase):
    """Test Cases for the ExpiredDataRemover object."""

    def test_initializer(self):
        """Test to init."""
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS)
        self.assertEqual(remover._months_to_keep, 3)
        self.assertEqual(remover._line_items_months, 1)
        remover2 = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS, 2, 2)
        self.assertEqual(remover2._months_to_keep, 2)
        self.assertEqual(remover2._line_items_months, 2)

    def test_initializer_ocp(self):
        """Test to init for OCP."""
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_OCP)
        self.assertEqual(remover._months_to_keep, 3)
        self.assertEqual(remover._line_items_months, 1)

    def test_initializer_azure(self):
        """Test to init for Azure."""
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AZURE)
        self.assertEqual(remover._months_to_keep, 3)
        self.assertEqual(remover._line_items_months, 1)

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
                "expected_expire": datetime(year=2018, month=4, day=1, tzinfo=pytz.UTC),
                "months_to_keep": None,
            },
            {
                "current_date": datetime(year=2018, month=7, day=31),
                "expected_expire": datetime(year=2018, month=4, day=1, tzinfo=pytz.UTC),
                "months_to_keep": None,
            },
            {
                "current_date": datetime(year=2018, month=3, day=20),
                "expected_expire": datetime(year=2017, month=12, day=1, tzinfo=pytz.UTC),
                "months_to_keep": None,
            },
            {
                "current_date": datetime(year=2018, month=7, day=1),
                "expected_expire": datetime(year=2017, month=7, day=1, tzinfo=pytz.UTC),
                "months_to_keep": 12,
            },
            {
                "current_date": datetime(year=2018, month=7, day=31),
                "expected_expire": datetime(year=2017, month=7, day=1, tzinfo=pytz.UTC),
                "months_to_keep": 12,
            },
            {
                "current_date": datetime(year=2018, month=3, day=20),
                "expected_expire": datetime(year=2016, month=3, day=1, tzinfo=pytz.UTC),
                "months_to_keep": 24,
            },
        ]
        for test_case in date_matrix:
            with patch.object(DateAccessor, "today", return_value=test_case.get("current_date")):
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

    @patch("masu.processor.expired_data_remover.AWSReportDBCleaner.purge_expired_line_item")
    def test_remove_provider_items_only(self, mock_purge):
        """Test that remove is called with provider_uuid items only."""
        provider_uuid = self.aws_provider_uuid
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS)
        date = remover._calculate_expiration_date(line_items_only=True)
        remover.remove(provider_uuid=provider_uuid, line_items_only=True)
        mock_purge.assert_called_with(expired_date=date, simulate=False, provider_uuid=provider_uuid)

    @patch("masu.processor.expired_data_remover.AWSReportDBCleaner.purge_expired_line_item")
    def test_remove_items_only(self, mock_purge):
        """Test that remove is called with provider_uuid items only."""
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS)
        date = remover._calculate_expiration_date(line_items_only=True)
        remover.remove(line_items_only=True)
        mock_purge.assert_called_with(expired_date=date, simulate=False)

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
            day_before_cutoff = expiration_date - relativedelta.relativedelta(days=1)
            dates = [current_month, day_before_cutoff, expiration_date]
            uuids = []
            uuids_to_be_deleted = []
            for date in dates:
                manifest_creation_datetime = current_month
                manifest_updated_datetime = manifest_creation_datetime + relativedelta.relativedelta(days=2)
                uuid = uuid4()
                data = {
                    "assembly_id": uuid,
                    "manifest_creation_datetime": manifest_creation_datetime,
                    "manifest_updated_datetime": manifest_updated_datetime,
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
        day_before_cutoff = expiration_date - relativedelta.relativedelta(days=1)
        day_before_cutoff_data = {
            "assembly_id": uuid4(),
            "manifest_creation_datetime": None,
            "manifest_updated_datetime": None,
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
        day_before_cutoff = expiration_date - relativedelta.relativedelta(days=1)
        fixture_records = [
            (self.aws_provider_uuid, expiration_date),  # not expired, should not delete
            (self.aws_provider_uuid, day_before_cutoff),  # expired, should delete
            (self.azure_provider_uuid, day_before_cutoff),  # expired, should not delete
        ]
        manifest_uuids = []
        manifest_uuids_to_be_deleted = []
        manifest_creation_datetime = current_month
        manifest_updated_datetime = manifest_creation_datetime + relativedelta.relativedelta(days=2)
        for fixture_record in fixture_records:
            manifest_uuid = uuid4()
            data = {
                "assembly_id": manifest_uuid,
                "manifest_creation_datetime": manifest_creation_datetime,
                "manifest_updated_datetime": manifest_updated_datetime,
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
        day_before_cutoff = expiration_date - relativedelta.relativedelta(days=1)
        manifest_id = 7766
        day_before_cutoff_data = {
            "id": manifest_id,
            "assembly_id": uuid4(),
            "manifest_creation_datetime": None,
            "manifest_updated_datetime": None,
            "billing_period_start_datetime": day_before_cutoff,
            "num_total_files": 1,
            "provider_id": self.aws_provider_uuid,
        }
        manifest_entry = CostUsageReportManifest(**day_before_cutoff_data)
        manifest_entry.save()
        manifest_helper = ManifestCreationHelper(
            manifest_id, manifest_entry.num_total_files, manifest_entry.assembly_id
        )
        manifest_helper.generate_test_report_files()
        manifest_helper.process_all_files()
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

    def test_remove_items_only_azure(self):
        """Test that remove is called with provider_uuid items only."""
        azure_types = [Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL]
        for az_type in azure_types:
            remover = ExpiredDataRemover(self.schema, az_type)
            result_no_provider = remover.remove(line_items_only=True)
            self.assertIsNone(result_no_provider)
            result_with_provider = remover.remove(line_items_only=True, provider_uuid="1234")
            self.assertIsNone(result_with_provider)
