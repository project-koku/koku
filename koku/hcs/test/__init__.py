"""Shared Class for masu tests."""
from api.iam.test.iam_test_case import IamTestCase
from api.models import Customer
from api.provider.models import Provider


class HCSTestCase(IamTestCase):
    """Subclass of TestCase that automatically create an app and client."""

    @classmethod
    def setUpClass(cls):
        """Create test case setup."""
        super().setUpClass()

        cls.schema = "org1234567"
        cls.acct = "10001"
        cls.org_id = "1234567"

    def setUp(self):
        """Set up each test case."""
        self.customer, __ = Customer.objects.get_or_create(account_id=self.acct, schema_name=self.schema)

        self.aws_provider = Provider.objects.filter(type=Provider.PROVIDER_AWS_LOCAL).first()
        self.azure_provider = Provider.objects.get(type=Provider.PROVIDER_AZURE_LOCAL)
        self.gcp_provider = Provider.objects.get(type=Provider.PROVIDER_GCP_LOCAL)

        self.aws_provider_type = self.aws_provider.type
        self.azure_provider_type = self.azure_provider.type
        self.gcp_provider_type = self.gcp_provider.type

        self.aws_provider_uuid = str(self.aws_provider.uuid)
        self.azure_provider_uuid = str(self.azure_provider.uuid)
        self.gcp_provider_uuid = str(self.gcp_provider.uuid)
