"""Shared Class for masu tests."""
from api.iam.test.iam_test_case import IamTestCase
from api.models import Customer
from api.provider.models import Provider


class MasuTestCase(IamTestCase):
    """Subclass of TestCase that automatically create an app and client."""

    @classmethod
    def setUpClass(cls):
        """Create test case setup."""
        super().setUpClass()

        cls.schema = "acct10001"
        cls.acct = "10001"

    def setUp(self):
        """Set up each test case."""
        self.customer, __ = Customer.objects.get_or_create(account_id=self.acct, schema_name=self.schema)

        self.aws_provider = Provider.objects.get(type=Provider.PROVIDER_AWS_LOCAL)
        self.ocp_provider = Provider.objects.filter(type=Provider.PROVIDER_OCP).first()
        self.azure_provider = Provider.objects.get(type=Provider.PROVIDER_AZURE_LOCAL)

        self.aws_provider_uuid = str(self.aws_provider.uuid)
        self.ocp_provider_uuid = str(self.ocp_provider.uuid)
        self.azure_provider_uuid = str(self.azure_provider.uuid)

        self.aws_test_provider_uuid = self.aws_provider_uuid
        self.azure_test_provider_uuid = self.azure_provider_uuid
        self.ocp_test_provider_uuid = self.ocp_provider_uuid

        self.ocp_provider_resource_name = self.ocp_provider.authentication.provider_resource_name

        self.ocp_db_auth_id = self.ocp_provider.authentication.id
        self.aws_db_auth_id = self.aws_provider.authentication.id
        self.azure_db_auth_id = self.azure_provider.authentication.id

        self.ocp_billing_source = self.ocp_provider.billing_source.id
        self.aws_billing_source = self.aws_provider.billing_source.id
        self.azure_billing_source = self.azure_provider.billing_source.id
