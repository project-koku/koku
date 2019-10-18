"""Test GCPReportProcessor."""
import uuid

from django.test import TestCase
from faker import Faker
from tenant_schemas.utils import schema_context

from api.models import CostModelMetricsMap, Customer, Tenant
from api.provider.models import Provider, ProviderAuthentication, ProviderBillingSource
from masu.external import UNCOMPRESSED
from masu.processor.gcp.gcp_report_processor import GCPReportProcessor
from reporting.provider.gcp.models import GCPProject, GCPCostEntryBill, GCPCostEntryLineItemDaily
from masu.external.date_accessor import DateAccessor


fake = Faker()


class GCPReportProcessorTest(TestCase):
    """Test Cases for the GCPReportProcessor object."""

    def setUp(self):
        """Set up each test."""
        self.schema = 'acct10001'
        self.acct = '10001'
        self.test_report = './koku/masu/test/data/gcp/evidence-2019-06-03.csv'

        self.date_accessor = DateAccessor()

        self.customer = Customer.objects.create(
            account_id=self.acct, schema_name=self.schema
        )

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

        self.assembly_id = '1234'
        self.processor = GCPReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_id=self.gcp_provider.id,
        )

    def test_gcp_process(self):
        """Test the processing of an uncompressed GCP file."""
        with schema_context(self.schema):

            self.assertFalse(GCPCostEntryLineItemDaily.objects.all().exists())
            self.processor.process()
            self.assertTrue(len(GCPCostEntryLineItemDaily.objects.all()) > 0)
            self.assertTrue(len(GCPProject.objects.all()) > 0)
            self.assertEquals(1, len(GCPCostEntryBill.objects.all()))
