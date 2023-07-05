"""Shared Class for SUBS tests."""
import uuid

from api.iam.test.iam_test_case import IamTestCase
from api.models import Customer
from api.models import Provider


class SUBSTestCase(IamTestCase):
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
        self.aws_provider_type = self.aws_provider.type
        self.aws_provider_uuid = str(self.aws_provider.uuid)
        self.tracing_id = str(uuid.uuid4())
