"""Shared Class for masu tests."""
from django.test import TestCase
from tenant_schemas.utils import schema_context

from api.models import Customer, Tenant
from api.provider.models import Provider, ProviderAuthentication, ProviderBillingSource


class MasuTestCase(TestCase):
    """Subclass of TestCase that automatically create an app and client."""

    @classmethod
    def setUpClass(cls):
        """Create test case setup."""
        super().setUpClass()
        with schema_context('public'):
            cls.schema = 'acct10001'
            cls.acct = '10001'
            cls.customer = Customer.objects.create(
                account_id=cls.acct, schema_name=cls.schema
            )
            cls.tenant = Tenant(schema_name=cls.schema)
            cls.tenant.save()
        self.aws_provider_id = 1
        self.ocp_provider_id = 2
        cls.ocp_test_provider_uuid = '3c6e687e-1a09-4a05-970c-2ccf44b0952e'
        cls.aws_test_provider_uuid = '6e212746-484a-40cd-bba0-09a19d132d64'
        cls.aws_provider_resource_name = 'arn:aws:iam::111111111111:role/CostManagement'
        cls.ocp_provider_resource_name = 'my-ocp-cluster-1'
        cls.aws_test_billing_source = 'test-bucket'
        cls.aws_auth_provider_uuid = '7e4ec31b-7ced-4a17-9f7e-f77e9efa8fd6'

        cls.aws_auth = ProviderAuthentication.objects.create(
            uuid=cls.aws_auth_provider_uuid,
            provider_resource_name=cls.aws_provider_resource_name,
        )
        cls.aws_auth.save()
        cls.aws_billing_source = ProviderBillingSource.objects.create(
            bucket=cls.aws_test_billing_source
        )
        cls.aws_billing_source.save()

        cls.aws_db_auth_id = cls.aws_auth.id

        cls.aws_provider = Provider.objects.create(
            uuid=cls.aws_test_provider_uuid,
            name='Test Provider',
            type='AWS',
            authentication=cls.aws_auth,
            billing_source=cls.aws_billing_source,
            customer=cls.customer,
            setup_complete=False,
        )
        cls.aws_provider.save()

        cls.ocp_auth = ProviderAuthentication.objects.create(
            uuid='7e4ec31b-7ced-4a17-9f7e-f77e9efa8fd7',
            provider_resource_name=cls.ocp_provider_resource_name,
        )
        cls.ocp_auth.save()
        cls.ocp_db_auth_id = cls.ocp_auth.id

        cls.ocp_provider = Provider.objects.create(
            uuid=cls.ocp_test_provider_uuid,
            name='Test Provider',
            type='OCP',
            authentication=cls.ocp_auth,
            customer=cls.customer,
            setup_complete=False,
        )
        cls.ocp_provider.save()
