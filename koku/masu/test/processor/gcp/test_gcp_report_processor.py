"""Test GCPReportProcessor."""
import os
import shutil
import tempfile
import uuid
from datetime import datetime
from unittest.mock import patch

import numpy as np
import pytz
from dateutil import parser
from django_tenants.utils import schema_context
from faker import Faker

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
from reporting.provider.gcp.models import GCPCostEntryLineItemDaily
from reporting.provider.gcp.models import GCPProject

fake = Faker()


class GCPReportProcessorTest(MasuTestCase):
    """Test Cases for the GCPReportProcessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.test_report_path = "./koku/masu/test/data/gcp/evidence-2019-06-03.csv"

        cls.date_accessor = DateAccessor()
        cls.manifest_accessor = ReportManifestDBAccessor()

    def setUp(self):
        """Set up GCP tests."""
        super().setUp()
        self.temp_dir = tempfile.mkdtemp()
        self.test_report = f"{self.temp_dir}/evidence-2019-06-03.csv"

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

        start_time = "2019-09-17T00:00:00-07:00"
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
        self.processor.process()
        with schema_context(self.schema):
            self.assertTrue(len(GCPCostEntryLineItemDaily.objects.all()) > 0)
            self.assertTrue(len(GCPProject.objects.all()) > 0)
            self.assertEquals(1, len(GCPCostEntryBill.objects.all()))
        self.assertFalse(os.path.exists(self.test_report))

    def test_create_gcp_cost_entry_bill(self):
        """Test calling _get_or_create_cost_entry_bill on an entry bill that doesn't exist creates it."""
        bill_row = {"Start Time": "2019-09-17T00:00:00-07:00"}
        entry_bill_id = self.processor._get_or_create_cost_entry_bill(bill_row, self.accessor)

        with schema_context(self.schema):
            self.assertTrue(GCPCostEntryBill.objects.filter(id=entry_bill_id).exists())

    def test_get_gcp_cost_entry_bill(self):
        """Test calling _get_or_create_cost_entry_bill on an entry bill that exists fetches its id."""
        start_time = "2019-09-17T00:00:00-07:00"
        report_date_range = utils.month_date_range(parser.parse(start_time))
        start_date, end_date = report_date_range.split("-")

        start_date_utc = parser.parse(start_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)
        end_date_utc = parser.parse(end_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)

        with schema_context(self.schema):
            entry_bill = GCPCostEntryBill.objects.create(
                provider=self.gcp_provider, billing_period_start=start_date_utc, billing_period_end=end_date_utc
            )
        entry_bill_id = self.processor._get_or_create_cost_entry_bill(
            {"Start Time": datetime.strftime(start_date_utc, "%Y-%m-%d %H:%M%z")}, self.accessor
        )
        self.assertEquals(entry_bill.id, entry_bill_id)

    def test_create_gcp_project(self):
        """Test calling _get_or_create_gcp_project on a project id that doesn't exist creates it."""
        project_data = {
            "Project ID": fake.word(),
            "Account ID": fake.word(),
            "Project Number": fake.pyint(),
            "Project Name": fake.word(),
        }
        project_id = self.processor._get_or_create_gcp_project(project_data, self.accessor)
        with schema_context(self.schema):
            self.assertTrue(GCPProject.objects.filter(id=project_id).exists())

    def test_get_gcp_project(self):
        """Test calling _get_or_create_gcp_project on a project id that exists gets it."""
        project_id = fake.word()
        account_id = fake.word()
        with schema_context(self.schema):
            project = GCPProject.objects.create(
                project_id=project_id, account_id=account_id, project_number=fake.pyint(), project_name=fake.word()
            )
        fetched_project_id = self.processor._get_or_create_gcp_project(
            {
                "Project ID": project_id,
                "Account ID": fake.word(),
                "Project Number": fake.pyint(),
                "Project Name": fake.word(),
            },
            self.accessor,
        )
        self.assertEquals(fetched_project_id, project.id)
        with schema_context(self.schema):
            # Even if _get_or_create_gcp_project is called with a different
            # account_id, but the same project_id, we expect account_id to remain the same
            gcp_project = GCPProject.objects.get(id=project.id)
            self.assertEquals(gcp_project.account_id, account_id)

    def test_gcp_process_twice(self):
        """Test the processing of an GCP file again, results in the same amount of objects."""
        self.processor.process()
        with schema_context(self.schema):
            num_line_items = len(GCPCostEntryLineItemDaily.objects.all())
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
            self.assertEquals(num_line_items, len(GCPCostEntryLineItemDaily.objects.all()))
            self.assertEquals(num_projects, len(GCPProject.objects.all()))
            self.assertEquals(num_bills, len(GCPCostEntryBill.objects.all()))

    def test_consolidate_line_items(self):
        """Test that logic for consolidating lines work."""
        line1 = {
            "int": fake.pyint(),
            "float": fake.pyfloat(),
            "date": datetime.now(),
            "npint": np.int64(fake.pyint()),
            "cost_entry_bill_id": fake.pyint(),
            "project_id": fake.pyint(),
        }
        line2 = {
            "int": fake.pyint(),
            "float": fake.pyfloat(),
            "date": datetime.now(),
            "npint": np.int64(fake.pyint()),
            "cost_entry_bill_id": fake.pyint(),
            "project_id": fake.pyint(),
        }
        consolidated_line = self.processor._consolidate_line_items(line1, line2)

        self.assertEquals(consolidated_line["int"], line1["int"] + line2["int"])
        self.assertEquals(consolidated_line["float"], line1["float"] + line2["float"])
        self.assertEquals(consolidated_line["npint"], line1["npint"] + line2["npint"])
        self.assertEquals(consolidated_line["date"], line1["date"])
        self.assertEquals(consolidated_line["cost_entry_bill_id"], line1["cost_entry_bill_id"])
        self.assertEquals(consolidated_line["project_id"], line1["project_id"])
