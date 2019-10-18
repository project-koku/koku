"""Test the GCPReportDBAccessor utility object."""
import uuid
from datetime import datetime

import pytz
from dateutil import parser
from faker import Faker
from tenant_schemas.utils import schema_context

from api.provider.models import Provider, ProviderAuthentication, ProviderBillingSource
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.external import UNCOMPRESSED
from masu.external.date_accessor import DateAccessor
from masu.processor.gcp.gcp_report_processor import GCPReportProcessor
from masu.test import MasuTestCase
from masu.util import common as utils
from reporting.provider.gcp.models import GCPProject, GCPCostEntryBill, GCPCostEntryLineItemDaily


fake =Faker()

class GCPReportDBAccessorTest(MasuTestCase):
    """Test Cases for the AzureReportDBAccessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        with ReportingCommonDBAccessor() as report_common_db:
            cls.column_map = report_common_db.column_map

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()

        gcp_auth = ProviderAuthentication.objects.create(
            credentials={"project-id": fake.word()}
        )
        gcp_billing_source = ProviderBillingSource.objects.create(
            data_source={
                "bucket": fake.word()
            }
        )
        self.gcp_provider = Provider.objects.create(
            uuid=uuid.uuid4(),
            name='Test Provider',
            type='GCP',
            authentication=gcp_auth,
            billing_source=gcp_billing_source,
            customer=self.customer,
            setup_complete=True,
        )

        start_time = '2019-09-17T00:00:00-07:00'
        report_date_range = utils.month_date_range(parser.parse(start_time))
        start_date, end_date = report_date_range.split('-')

        self.start_date_utc = parser.parse(start_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)
        self.end_date_utc = parser.parse(end_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)

        self.assembly_id = '1234'
        self.manifest_dict = {
            'assembly_id': self.assembly_id,
            'billing_period_start_datetime': self.start_date_utc,
            'num_total_files': 1,
            'provider_id': self.gcp_provider.id,
        }
        manifest_accessor = ReportManifestDBAccessor()
        self.manifest = manifest_accessor.add(**self.manifest_dict)
        self.accessor = GCPReportDBAccessor(self.schema, self.column_map)

    def test_get_cost_entry_bills_query_by_provider(self):
        """Test that GCP bills are returned."""
        with schema_context(self.schema):
            GCPCostEntryBill.objects.create(
                billing_period_start=self.start_date_utc,
                billing_period_end=self.end_date_utc,
                provider_id=self.gcp_provider.id
            )
            bills = self.accessor.get_cost_entry_bills_query_by_provider(
                provider_id=self.gcp_provider.id
            )
            self.assertEquals(1, len(bills))

    def test_get_lineitem_query_for_billid(self):
        """Test that GCP line items matching bill_id are returned."""
        with schema_context(self.schema):
            bill = GCPCostEntryBill.objects.create(
                billing_period_start=self.start_date_utc,
                billing_period_end=self.end_date_utc,
                provider_id=self.gcp_provider.id
            )
            project = GCPProject.objects.create(
                project_id=fake.word(),
                account_id=fake.word(),
                project_number=fake.pyint(),
                project_name=fake.word()
            )
            for _ in range(10):
                GCPCostEntryLineItemDaily.objects.create(
                    start_time=self.start_date_utc,
                    line_item_type=fake.word(),
                    project=project,
                    cost_entry_bill=bill,
                    measurement_type=fake.word(),
                    consumption=fake.pyint(),
                    currency=fake.word(),
                    end_time=self.end_date_utc
                )
            line_items = self.accessor.get_lineitem_query_for_billid(
                bill_id=bill.id
            )
            self.assertEquals(10, len(line_items))
