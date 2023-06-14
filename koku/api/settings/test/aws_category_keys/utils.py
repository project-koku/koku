from django_tenants.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.report.test.util.constants import AWS_CONSTANTS
from reporting.provider.aws.models import AWSEnabledCategoryKeys


class TestAwsCategoryClass(IamTestCase):
    """Test aws category pieces."""

    def setUp(self):
        """Provides values needed for aws category tests."""
        super().setUp()
        self.aws_category_tuple = AWS_CONSTANTS["cost_category"]
        aws_cat_dict = self.aws_category_tuple[0]
        self.keys = aws_cat_dict.keys()
        self.key = list(self.keys)[0]
        with tenant_context(self.tenant):
            cat_key_row = AWSEnabledCategoryKeys.objects.filter(key=self.key).first()
            self.enabled = cat_key_row.enabled
            self.uuid = cat_key_row.uuid

    def check_key_enablement(self, key=None):
        if not key:
            key = self.key
        with tenant_context(self.tenant):
            cat_key_row = AWSEnabledCategoryKeys.objects.filter(key=key).first()
            return cat_key_row.enabled
