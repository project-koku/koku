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

import pytz

from api.models import Provider
from masu.external.date_accessor import DateAccessor
from masu.processor.expired_data_remover import ExpiredDataRemover
from masu.processor.expired_data_remover import ExpiredDataRemoverError
from masu.test import MasuTestCase
from dateutil import relativedelta
from uuid import uuid4
from reporting_common.models import CostUsageReportManifest


class ExpiredDataRemoverTest(MasuTestCase):
    """Test Cases for the ExpiredDataRemover object."""

    def test_initializer(self):
        """Test to init."""
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS)
        self.assertEqual(remover._months_to_keep, 3)
        self.assertIsInstance(remover._expiration_date, datetime)

    def test_initializer_ocp(self):
        """Test to init for OCP."""
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_OCP)
        self.assertEqual(remover._months_to_keep, 3)
        self.assertIsInstance(remover._expiration_date, datetime)

    def test_initializer_azure(self):
        """Test to init for Azure."""
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AZURE)
        self.assertEqual(remover._months_to_keep, 3)
        self.assertIsInstance(remover._expiration_date, datetime)

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

    def test_delete_expired_cost_usage_report_manifest(self):
        """
        Test remove manifests that are expired.

        All providers should be affected.

        This test inserts CostUsageReports and then deletes all of them that are older than
        the specified expired_date.
        """
        # expired_date = 3monthsago
        provider_uuid = self.aws_provider_uuid
        # insertMockCostUsageReports(provider=provider_uuid)
        ## Insert Mock CostUsageReportManifests
        # A time for a record which should not be deleted
        this_month = datetime.today().replace(day=1)
        start = this_month
        cutoff_two_months_ago = this_month - relativedelta.relativedelta(months=2)  # the expired_date
        day_before_cutoff = cutoff_two_months_ago - relativedelta.relativedelta(days=1)

        # A time for a record which should be deleted in this test.
        # Record A
        manifest_creation_datetime = this_month
        manifest_updated_datetime = manifest_creation_datetime + relativedelta.relativedelta(days=2)
        record_a_uuid = uuid4()
        data = {
            "assembly_id": record_a_uuid,
            "manifest_creation_datetime": manifest_creation_datetime,
            "manifest_updated_datetime": manifest_updated_datetime,
            "billing_period_start_datetime": start,
            "num_processed_files": 1,
            "num_total_files": 1,
            "provider_id": provider_uuid,
        }
        manifest_entry = CostUsageReportManifest(**data)
        manifest_entry.save()
        manifest_entries = CostUsageReportManifest.objects.all()
        assert len(manifest_entries) == 1
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
        manifest_entries = CostUsageReportManifest.objects.all()
        assert len(manifest_entries) == 2

        # Record C
        # This record should not get deleted as it occurs on the date of the expiration, not before.
        record_c_uuid = uuid4()
        data_day_of_expiration = {
            "assembly_id": record_c_uuid,
            "manifest_creation_datetime": manifest_creation_datetime,
            "manifest_updated_datetime": manifest_updated_datetime,
            "billing_period_start_datetime": cutoff_two_months_ago,  # Don't delete me!
            "num_processed_files": 1,
            "num_total_files": 1,
            "provider_id": provider_uuid,
        }
        manifest_entry_3 = CostUsageReportManifest(**data_day_of_expiration)
        manifest_entry_3.save()
        manifest_entries = CostUsageReportManifest.objects.all()
        assert len(manifest_entries) == 3

        cleaner.purge_expired_report_data(self, expired_date=None, provider_uuid=None, simulate=False)
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS)
        remover.remove(provider_uuid=provider_uuid)

        # Check if record A still exists (it should):
        record_a = CostUsageReportManifest.objects.filter(assembly_id=record_a_uuid)
        self.assertEqual(len(record_a), 1)
        record_b = CostUsageReportManifest.objects.filter(assembly_id=record_b_uuid)
        self.assertEqual(len(record_b), 0)
        record_c = CostUsageReportManifest.objects.filter(assembly_id=record_c_uuid)
        self.assertEqual(len(record_c), 1)

        # # manifest_data_list = CostUsageReportManifest.objects.filter(billing_period=4monthsago).all()
        # manifest_months_query = CostUsageReportManifest.objects.order_by(
        #     "billing_period_start_datetime"
        # ).all()  # Get all the manifests.
        # # manifests_older_than_expired_date = CostUsageReportManifest.objects.filter(billing_period_date_lt=datetime.datetime.4monthsago)
        # self.assertEqual(len(manifest_data_list), 0)

    def test_expired_data_does_not_delete_data_before_cutoff(self):
        """
        Test that the deletion of expired data does not remove data after the expired date.

        # For example, if today is 2-15-2019 and there are three records
        # And the expired_date is 12-1-2019, then all records in November and before would be deleted.
        # All records in December would not be deleted.
        # All CostUsageReportManifest records in November and all previous months and years would be deleted in all providers.

        Record 1: billing_period_start_datetime = 2-1-2019  (not expired)
        Record 2: billing_period_start_datetime = 12-1-2019 (not expired)
        Record 3: billing_period_start_datetime = 11-31-2019 (expired)
        """
        assert False

