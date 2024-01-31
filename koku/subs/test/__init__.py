"""Shared Class for subs tests."""
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider


class SUBSTestCase(IamTestCase):
    """Subclass of TestCase that automatically create an app and client."""

    @classmethod
    def setUpClass(cls):
        """Create test case setup."""
        super().setUpClass()

        cls.schema = "org1234567"
        cls.acct = "10001"
        cls.org_id = "1234567"

        cls.aws_provider = Provider.objects.filter(type=Provider.PROVIDER_AWS_LOCAL).first()
        cls.aws_provider_type = Provider.PROVIDER_AWS_LOCAL

        cls.azure_provider = Provider.objects.filter(type=Provider.PROVIDER_AZURE_LOCAL).first()
        cls.azure_tenant = cls.azure_provider.account.get("credentials").get("tenant_id")
        cls.azure_provider_type = Provider.PROVIDER_AZURE_LOCAL
