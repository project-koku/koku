"""Shared Class for masu tests."""
from api.iam.test.iam_test_case import IamTestCase


class HCSTestCase(IamTestCase):
    """Subclass of TestCase that automatically create an app and client."""

    @classmethod
    def setUpClass(cls):
        """Create test case setup."""
        super().setUpClass()

        cls.schema = "acct10001"
        cls.acct = "10001"
