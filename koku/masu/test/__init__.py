"""Shared Class for masu tests."""
import json
import pkgutil

from django.db import connection, connections
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase
from tenant_schemas.utils import schema_context

from api.models import CostModelMetricsMap, Customer, Tenant
from api.provider.models import Provider, ProviderAuthentication, ProviderBillingSource
from reporting_common.models import ReportColumnMap

def load_db_map_data():
    if ReportColumnMap.objects.count() == 0:
        data = pkgutil.get_data('reporting_common',
                                'data/aws_report_column_map.json')
        data = json.loads(data)
        for entry in data:
            map = ReportColumnMap(**entry)
            map.save()

        data = pkgutil.get_data('reporting_common',
                                'data/ocp_report_column_map.json')
        data = json.loads(data)
        for entry in data:
            map = ReportColumnMap(**entry)
            map.save()

    if CostModelMetricsMap.objects.count() == 0:
        data = pkgutil.get_data('api',
                                'metrics/data/cost_models_metric_map.json')
        data = json.loads(data)
        for entry in data:
            map = CostModelMetricsMap(**entry)
            map.save()


class MasuTestCase(TransactionTestCase):
    """Subclass of TestCase that automatically create an app and client."""

    @classmethod
    def setUpClass(cls):
        """Create test case setup."""
        super().setUpClass()

        cls.schema = 'acct10001'
        cls.acct = '10001'
        # cls.customer = Customer.objects.create(
        #     account_id=cls.acct, schema_name=cls.schema
        # )
        cursor = connection.cursor()
        cursor.execute(
            """SELECT tablename FROM pg_tables WHERE schemaname = %s""",
            [cls.schema]
        )
        result = cursor.fetchall()
        if not result:
            cls.tenant = Tenant(schema_name=cls.schema)
            cls.tenant.save()
        
        # Load static data into the DB
        # E.g. report column maps
        load_db_map_data()
        
        cls.ocp_test_provider_uuid = '3c6e687e-1a09-4a05-970c-2ccf44b0952e'
        cls.aws_test_provider_uuid = '6e212746-484a-40cd-bba0-09a19d132d64'
        cls.azure_test_provider_uuid = 'b16c111a-d05f-488c-a6d9-c2a6f3ee02bb'
        cls.aws_provider_resource_name = 'arn:aws:iam::111111111111:role/CostManagement'
        cls.ocp_provider_resource_name = 'my-ocp-cluster-1'
        cls.aws_test_billing_source = 'test-bucket'
        cls.ocp_test_billing_source = None
        cls.aws_auth_provider_uuid = '7e4ec31b-7ced-4a17-9f7e-f77e9efa8fd6'
        cls.azure_credentials = {
            "subscription_id": "e03f27e2-f248-4ad7-bfb1-9a4cff600e1d",
            "tenant_id": "67b2fcf4-228a-4aee-a215-3a768cdd0105",
            "client_id": "fac9449a-0f78-42bb-b8e5-90144a025191",
            "client_secret": "secretcode"
        }
        cls.azure_data_source = {"resource_group": "resourcegroup1", "storage_account": "storageaccount1"}

    @classmethod
    def tearDownClass(cls):
        """Tear down the class."""
        connection.set_schema_to_public()
        super().tearDownClass()

    def setUp(self):
        """Set up each test case."""
        self.customer = Customer.objects.create(
            account_id=self.acct, schema_name=self.schema
        )

        self.aws_auth = ProviderAuthentication.objects.create(
            uuid=self.aws_auth_provider_uuid,
            provider_resource_name=self.aws_provider_resource_name,
        )
        self.aws_auth.save()
        self.aws_billing_source = ProviderBillingSource.objects.create(
            bucket=self.aws_test_billing_source
        )
        self.aws_billing_source.save()

        self.aws_db_auth_id = self.aws_auth.id

        self.aws_provider = Provider.objects.create(
            uuid=self.aws_test_provider_uuid,
            name='Test Provider',
            type='AWS',
            authentication=self.aws_auth,
            billing_source=self.aws_billing_source,
            customer=self.customer,
            setup_complete=False,
        )
        self.aws_provider.save()

        self.ocp_auth = ProviderAuthentication.objects.create(
            uuid='7e4ec31b-7ced-4a17-9f7e-f77e9efa8fd7',
            provider_resource_name=self.ocp_provider_resource_name,
        )
        self.ocp_auth.save()
        self.ocp_db_auth_id = self.ocp_auth.id

        self.ocp_provider = Provider.objects.create(
            uuid=self.ocp_test_provider_uuid,
            name='Test Provider',
            type='OCP',
            authentication=self.ocp_auth,
            customer=self.customer,
            setup_complete=False,
        )
        self.ocp_provider.save()

        self.azure_auth = ProviderAuthentication.objects.create(
            credentials=self.azure_credentials
        )
        self.azure_auth.save()

        self.azure_billing_source = ProviderBillingSource.objects.create(
            data_source=self.azure_data_source
        )
        self.azure_billing_source.save()

        self.aws_provider_id = self.aws_provider.id
        self.ocp_provider_id = self.ocp_provider.id

        self.azure_provider = Provider.objects.create(
            uuid=self.azure_test_provider_uuid,
            name='Test Provider',
            type='AZURE',
            authentication=self.azure_auth,
            billing_source=self.azure_billing_source,
            customer=self.customer,
            setup_complete=False,
        )
        self.azure_provider.save()
        self.azure_provider_id = self.azure_provider.id

        # Load static data into the DB
        # E.g. report column maps
        load_db_map_data()

    def tearDown(self):
        """Tear down and restore database on the tenant schema."""
        connection.set_schema(self.schema)
        for db_name in self._databases_names(include_mirrors=False):
            # Flush the tenant schema's data
            call_command('flush', verbosity=0, interactive=False,
                         database=db_name, reset_sequences=False,
                         allow_cascade=self.available_apps is not None,
                         inhibit_post_migrate=False)
        connection.set_schema_to_public()
