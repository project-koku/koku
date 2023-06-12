"""Shared Class for SUBS tests."""
from api.iam.test.iam_test_case import IamTestCase


class SUBSTestCase(IamTestCase):
    """Subclass of TestCase that automatically create an app and client."""

    @classmethod
    def setUpClass(cls):
        """Create test case setup."""
        super().setUpClass()

        cls.schema = "org1234567"
        cls.acct = "10001"
        cls.org_id = "1234567"
