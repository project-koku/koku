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
        self.unkown_test_provider_uuid = "cabfdddb-4ed5-421e-a041-311b75daf235"

        self.ocp_on_aws_ocp_provider = Provider.objects.filter(
            infrastructure__infrastructure_type=Provider.PROVIDER_AWS_LOCAL
        ).first()
        self.ocp_on_azure_ocp_provider = Provider.objects.filter(
            infrastructure__infrastructure_type=Provider.PROVIDER_AZURE_LOCAL
        ).first()

        self.aws_provider_uuid = str(self.aws_provider.uuid)
        self.ocp_provider_uuid = str(self.ocp_provider.uuid)
        self.azure_provider_uuid = str(self.azure_provider.uuid)

        self.aws_test_provider_uuid = self.aws_provider_uuid
        self.azure_test_provider_uuid = self.azure_provider_uuid
        self.ocp_test_provider_uuid = self.ocp_provider_uuid

        self.ocp_provider_resource_name = self.ocp_provider.authentication.provider_resource_name

        self.ocp_db_auth = self.ocp_provider.authentication
        self.aws_db_auth = self.aws_provider.authentication
        self.azure_db_auth = self.azure_provider.authentication

        self.ocp_billing_source = self.ocp_provider.billing_source
        self.aws_billing_source = self.aws_provider.billing_source
        self.azure_billing_source = self.azure_provider.billing_source
