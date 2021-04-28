#
# Copyright 2020 Red Hat, Inc.
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
"""Test GCPReportProcessor."""
import csv
import os
import shutil
import tempfile
import uuid
from unittest.mock import patch

import pytz
from dateutil import parser
from django.db.utils import InternalError
from faker import Faker
from tenant_schemas.utils import schema_context

from api.provider.models import Provider
from api.provider.models import ProviderAuthentication
from api.provider.models import ProviderBillingSource
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external import UNCOMPRESSED
from masu.external.date_accessor import DateAccessor
from masu.processor.gcp.gcp_report_processor import GCPReportProcessor
from masu.test import MasuTestCase
from masu.util import common as utils
from reporting.provider.gcp.models import GCPCostEntryBill
from reporting.provider.gcp.models import GCPCostEntryLineItem
from reporting.provider.gcp.models import GCPProject

fake = Faker()


class GCPReportProcessorTest(MasuTestCase):
    """Test Cases for the GCPReportProcessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.test_report_path = (
            "./koku/masu/test/data/gcp/202011_30c31bca571d9b7f3b2c8459dd8bc34a_2020-11-08:2020-11-11.csv"
        )

        cls.date_accessor = DateAccessor()
        cls.manifest_accessor = ReportManifestDBAccessor()

    def setUp(self):
        """Set up GCP tests."""
        super().setUp()
        self.temp_dir = tempfile.mkdtemp()
        self.test_report = f"{self.temp_dir}/202011_30c31bca571d9b7f3b2c8459dd8bc34a_2020-11-08:2020-11-11.csv"

        shutil.copy2(self.test_report_path, self.test_report)

        gcp_auth = ProviderAuthentication.objects.create(credentials={"project-id": fake.word()})
        gcp_billing_source = ProviderBillingSource.objects.create(data_source={"bucket": fake.word()})
        with patch("masu.celery.tasks.check_report_updates"):
            self.gcp_provider = Provider.objects.create(
                uuid=uuid.uuid4(),
                name="Test Provider",
                type=Provider.PROVIDER_GCP,
                authentication=gcp_auth,
                billing_source=gcp_billing_source,
                customer=self.customer,
                setup_complete=True,
            )

        start_time = "2020-11-08 23:00:00+00:00"
        report_date_range = utils.month_date_range(parser.parse(start_time))
        start_date, end_date = report_date_range.split("-")

        self.start_date_utc = parser.parse(start_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)
        self.end_date_utc = parser.parse(end_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)

        self.assembly_id = "1234"
        self.manifest_dict = {
            "assembly_id": self.assembly_id,
            "billing_period_start_datetime": self.start_date_utc,
            "num_total_files": 1,
            "provider_uuid": self.gcp_provider.uuid,
        }
        manifest_accessor = ReportManifestDBAccessor()
        self.manifest = manifest_accessor.add(**self.manifest_dict)

        self.processor = GCPReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.gcp_provider.uuid,
            manifest_id=self.manifest.id,
        )
        self.accessor = GCPReportDBAccessor(self.schema)

    def tearDown(self):
        """Tear down test case."""
        super().tearDown()
        shutil.rmtree(self.temp_dir)

    def test_gcp_process(self):
        """Test the processing of an GCP file writes objects to the database."""
        with schema_context(self.schema):
            expected_bill_count = len(GCPCostEntryBill.objects.all()) + 1
        self.processor.process()
        with schema_context(self.schema):
            self.assertTrue(len(GCPCostEntryLineItem.objects.all()) > 0)
            self.assertTrue(len(GCPProject.objects.all()) > 0)
            self.assertEquals(expected_bill_count, len(GCPCostEntryBill.objects.all()))
        self.assertFalse(os.path.exists(self.test_report))

    def test_create_gcp_cost_entry_bill(self):
        """Test calling _get_or_create_cost_entry_bill on an entry bill that doesn't exist creates it."""
        bill_row = {"invoice.month": "202011"}
        entry_bill_id = self.processor._get_or_create_cost_entry_bill(bill_row, self.accessor)

        with schema_context(self.schema):
            self.assertTrue(GCPCostEntryBill.objects.filter(id=entry_bill_id).exists())

    def test_get_gcp_cost_entry_bill(self):
        """Test calling _get_or_create_cost_entry_bill on an entry bill that exists fetches its id."""
        start_time = "2020-11-01 00:00:00+00"
        report_date_range = utils.month_date_range(parser.parse(start_time))
        start_date, end_date = report_date_range.split("-")

        start_date_utc = parser.parse(start_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)
        end_date_utc = parser.parse(end_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)

        with schema_context(self.schema):
            entry_bill = GCPCostEntryBill.objects.create(
                provider=self.gcp_provider, billing_period_start=start_date_utc, billing_period_end=end_date_utc
            )
        entry_bill_id = self.processor._get_or_create_cost_entry_bill({"invoice.month": "202011"}, self.accessor)
        self.assertEquals(entry_bill.id, entry_bill_id)

    def test_create_gcp_project(self):
        """Test calling _get_or_create_gcp_project on a project id that doesn't exist creates it."""
        project_data = {"project.id": fake.word(), "billing_account_id": fake.word(), "project.name": fake.word()}
        project_id = self.processor._get_or_create_gcp_project(project_data, self.accessor)
        with schema_context(self.schema):
            self.assertTrue(GCPProject.objects.filter(id=project_id).exists())

    def test_create_gcp_project_name_change(self):
        """Test changing the project name will update in the table."""
        project_id = fake.word()
        project_info = {"project.id": project_id, "billing_account_id": fake.word(), "project.name": fake.word()}
        expected_name = "BiggoStormsMixTape"
        pt_id_1 = self.processor._get_or_create_gcp_project(project_info, self.accessor)
        with schema_context(self.schema):
            self.assertTrue(GCPProject.objects.filter(id=pt_id_1).exists())
        project_info["project.name"] = expected_name
        pt_id_2 = self.processor._get_or_create_gcp_project(project_info, self.accessor)
        # Check that both calls return the same project table id
        self.assertEqual(pt_id_1, pt_id_2)
        with schema_context(self.schema):
            p = GCPProject.objects.filter(project_id=project_id).first()
            self.assertEqual(p.project_name, expected_name)

    def test_get_gcp_project(self):
        """Test calling _get_or_create_gcp_project on a project id that exists gets it."""
        project_id = fake.word()
        account_id = fake.word()
        project_name = fake.word()
        with schema_context(self.schema):
            project = GCPProject.objects.create(
                project_id=project_id, account_id=account_id, project_name=project_name
            )
        fetched_project_id = self.processor._get_or_create_gcp_project(
            {"project.id": project_id, "billing_account_id": account_id, "project.name": project_name}, self.accessor
        )
        self.assertEquals(fetched_project_id, project.id)
        with schema_context(self.schema):
            gcp_project = GCPProject.objects.get(id=project.id)
            self.assertEquals(gcp_project.account_id, account_id)
            self.assertEquals(gcp_project.project_name, project_name)

    def test_gcp_process_can_run_twice(self):
        """Test that row duplicates are inserted into the DB when process called twice."""
        self.processor.process()
        shutil.copy2(self.test_report_path, self.test_report)
        try:
            self.processor.process()
        except InternalError:
            self.fail("failed to call process twice.")

    def test_gcp_process_twice(self):
        """Test the processing of an GCP file again, results in the same amount of objects."""
        self.processor.process()
        with schema_context(self.schema):
            num_line_items = len(GCPCostEntryLineItem.objects.all())
            num_projects = len(GCPProject.objects.all())
            num_bills = len(GCPCostEntryBill.objects.all())

        # Why another processor instance? because calling process() with the same processor instance fails
        # django.db.utils.InternalError: no such savepoint.

        shutil.copy2(self.test_report_path, self.test_report)

        processor = GCPReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.gcp_provider.uuid,
            manifest_id=self.manifest.id,
        )
        processor.process()
        with schema_context(self.schema):
            self.assertEquals(num_line_items, len(GCPCostEntryLineItem.objects.all()))
            self.assertEquals(num_projects, len(GCPProject.objects.all()))
            self.assertEquals(num_bills, len(GCPCostEntryBill.objects.all()))

    def test_no_report_path(self):
        """Test error caught when report path doesn't exist."""
        processor = GCPReportProcessor(
            schema_name=self.schema,
            report_path="/path/does/not/exist/202011_123_2020-11-08:2020-11-11.csv",
            compression=UNCOMPRESSED,
            provider_uuid=self.gcp_provider.uuid,
            manifest_id=self.manifest.id,
        )
        result = processor.process()
        self.assertFalse(result)

    def test_no_manifest_process(self):
        """Test that we can success process reports without manifest."""
        with schema_context(self.schema):
            expected_bill_count = len(GCPCostEntryBill.objects.all()) + 1
        processor = GCPReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.gcp_provider.uuid,
        )
        processor.process()
        with schema_context(self.schema):
            self.assertTrue(len(GCPCostEntryLineItem.objects.all()) > 0)
            self.assertTrue(len(GCPProject.objects.all()) > 0)
            self.assertEquals(expected_bill_count, len(GCPCostEntryBill.objects.all()))
        self.assertFalse(os.path.exists(self.test_report))

    def test_create_cost_entry_line_item_bad_time(self):
        """Test time parse errors are caught correctly."""
        processor = GCPReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_uuid=self.gcp_provider.uuid,
        )
        with open(self.test_report) as csvfile:
            reader = csv.DictReader(csvfile)
            row_one = next(reader)
        fake_id = 2
        row_one["usage_start_time"] = "bad time value"
        processor._create_cost_entry_line_item(row_one, fake_id, fake_id, self.accessor, fake_id)
        self.assertFalse(processor.processed_report.requested_partitions)
        del row_one["usage_start_time"]
        processor._create_cost_entry_line_item(row_one, fake_id, fake_id, self.accessor, fake_id)
        self.assertFalse(processor.processed_report.requested_partitions)

    def test_gcp_process_empty_file(self):
        """Test the processing of an GCP file again, results in the same amount of objects."""
        with schema_context(self.schema):
            num_line_items = len(GCPCostEntryLineItem.objects.all())
            num_projects = len(GCPProject.objects.all())
            num_bills = len(GCPCostEntryBill.objects.all())
        f = open(self.test_report, "w")
        f.truncate()
        f.write("invoice.month,project.id")
        f.close()
        result = self.processor.process()
        self.assertTrue(result)
        with schema_context(self.schema):
            self.assertEquals(num_line_items, len(GCPCostEntryLineItem.objects.all()))
            self.assertEquals(num_projects, len(GCPProject.objects.all()))
            self.assertEquals(num_bills, len(GCPCostEntryBill.objects.all()))
