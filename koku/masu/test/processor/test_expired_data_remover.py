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
from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

import pytz
from dateutil import relativedelta

from api.models import Provider
from masu.external.date_accessor import DateAccessor
from masu.processor.expired_data_remover import ExpiredDataRemover
from masu.processor.expired_data_remover import ExpiredDataRemoverError
from masu.test import MasuTestCase
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

        def insert_and_assert_delete_cost_usage_manifests(provider_type, provider_uuid):
            """
            Insert CostUsageReportManifests for a specific provider.

            Assert that the expired records for that provider are deleted.
            """
            remover = ExpiredDataRemover(self.schema, provider_type)
            expiration_date = remover._calculate_expiration_date()
            this_month = datetime.today().replace(day=1)
            day_before_cutoff = expiration_date - relativedelta.relativedelta(days=1)

            # Record A
            manifest_creation_datetime = this_month
            manifest_updated_datetime = manifest_creation_datetime + relativedelta.relativedelta(days=2)
            record_a_uuid = uuid4()
            data = {
                "assembly_id": record_a_uuid,
                "manifest_creation_datetime": manifest_creation_datetime,
                "manifest_updated_datetime": manifest_updated_datetime,
                "billing_period_start_datetime": this_month,
                "num_processed_files": 1,
                "num_total_files": 1,
                "provider_id": provider_uuid,
            }
            manifest_entry = CostUsageReportManifest(**data)
            manifest_entry.save()

            # Record B
            # This record should be deleted because the billing_period_start_datetime
            # is before the expiration_date
            record_b_uuid = uuid4()
            day_before_cutoff_data = {
                "assembly_id": record_b_uuid,
                "manifest_creation_datetime": manifest_creation_datetime,
                "manifest_updated_datetime": manifest_updated_datetime,
                "billing_period_start_datetime": day_before_cutoff,
                "num_processed_files": 1,
                "num_total_files": 1,
                "provider_id": provider_uuid,
            }
            manifest_entry_2 = CostUsageReportManifest(**day_before_cutoff_data)
            manifest_entry_2.save()

            # Record C
            # This record should not get deleted as it occurs on the date of the expiration, not before.
            record_c_uuid = uuid4()
            day_of_expiration_data = {
                "assembly_id": record_c_uuid,
                "manifest_creation_datetime": manifest_creation_datetime,
                "manifest_updated_datetime": manifest_updated_datetime,
                "billing_period_start_datetime": expiration_date,
                "num_processed_files": 1,
                "num_total_files": 1,
                "provider_id": provider_uuid,
            }
            manifest_entry_3 = CostUsageReportManifest(**day_of_expiration_data)
            manifest_entry_3.save()

            remover.remove()
            # Check if record A and C still exist. B should be deleted.
            record_a = CostUsageReportManifest.objects.filter(assembly_id=record_a_uuid)
            self.assertEqual(1, len(record_a))
            record_b = CostUsageReportManifest.objects.filter(assembly_id=record_b_uuid)
            self.assertEqual(0, len(record_b))
            record_c = CostUsageReportManifest.objects.filter(assembly_id=record_c_uuid)
            self.assertEqual(1, len(record_c))

        insert_and_assert_delete_cost_usage_manifests(Provider.PROVIDER_AWS, self.aws_provider_uuid)
        insert_and_assert_delete_cost_usage_manifests(Provider.PROVIDER_AZURE, self.azure_provider_uuid)
        insert_and_assert_delete_cost_usage_manifests(Provider.PROVIDER_OCP, self.ocp_provider_uuid)

        # There should be 6 records left, after the insertion of 9 records, and the deletion of 3.
        self.assertEqual(6, len(CostUsageReportManifest.objects.all()))

    def test_simulate_delete_expired_cost_usage_report_manifest(self):
        """
        Test that expired CostUsageReportManifests are removed.

        This test inserts CostUsageReportManifest objects,
        And then deletes CostUsageReportManifest objects older than
        the calculated expiration_date.
        """

        def insert_and_assert_delete_cost_usage_manifests(provider_type, provider_uuid):
            """
            Insert CostUsageReportManifests for a specific provider.

            Assert that the expired records for that provider are deleted.
            """

            remover = ExpiredDataRemover(self.schema, provider_type)
            expiration_date = remover._calculate_expiration_date()
            this_month = datetime.today().replace(day=1)
            day_before_cutoff = expiration_date - relativedelta.relativedelta(days=1)

            # Record A
            manifest_creation_datetime = this_month
            manifest_updated_datetime = manifest_creation_datetime + relativedelta.relativedelta(days=2)
            record_a_uuid = uuid4()
            data = {
                "assembly_id": record_a_uuid,
                "manifest_creation_datetime": manifest_creation_datetime,
                "manifest_updated_datetime": manifest_updated_datetime,
                "billing_period_start_datetime": this_month,
                "num_processed_files": 1,
                "num_total_files": 1,
                "provider_id": provider_uuid,
            }
            manifest_entry = CostUsageReportManifest(**data)
            manifest_entry.save()

            # Record B
            # This record should be deleted because the billing_period_start_datetime
            # is before the expiration_date
            record_b_uuid = uuid4()
            day_before_cutoff_data = {
                "assembly_id": record_b_uuid,
                "manifest_creation_datetime": manifest_creation_datetime,
                "manifest_updated_datetime": manifest_updated_datetime,
                "billing_period_start_datetime": day_before_cutoff,
                "num_processed_files": 1,
                "num_total_files": 1,
                "provider_id": provider_uuid,
            }
            manifest_entry_2 = CostUsageReportManifest(**day_before_cutoff_data)
            manifest_entry_2.save()

            # Record C
            # This record should not get deleted as it occurs on the date of the expiration, not before.
            record_c_uuid = uuid4()
            day_of_expiration_data = {
                "assembly_id": record_c_uuid,
                "manifest_creation_datetime": manifest_creation_datetime,
                "manifest_updated_datetime": manifest_updated_datetime,
                "billing_period_start_datetime": expiration_date,
                "num_processed_files": 1,
                "num_total_files": 1,
                "provider_id": provider_uuid,
            }
            manifest_entry_3 = CostUsageReportManifest(**day_of_expiration_data)
            manifest_entry_3.save()

            remover.remove(simulate=True)
            # Check if record A and C still exist. B should be deleted.
            record_a = CostUsageReportManifest.objects.filter(assembly_id=record_a_uuid)
            self.assertEqual(1, len(record_a))
            record_b = CostUsageReportManifest.objects.filter(assembly_id=record_b_uuid)
            self.assertEqual(1, len(record_b))
            record_c = CostUsageReportManifest.objects.filter(assembly_id=record_c_uuid)
            self.assertEqual(1, len(record_c))

        insert_and_assert_delete_cost_usage_manifests(Provider.PROVIDER_AWS, self.aws_provider_uuid)
        insert_and_assert_delete_cost_usage_manifests(Provider.PROVIDER_AZURE, self.azure_provider_uuid)
        insert_and_assert_delete_cost_usage_manifests(Provider.PROVIDER_OCP, self.ocp_provider_uuid)

        # There should be 6 records left, after the insertion of 9 records, and the deletion of 3.
        self.assertEqual(9, len(CostUsageReportManifest.objects.all()))
