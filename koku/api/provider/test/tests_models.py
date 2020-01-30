#
# Copyright 2019 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Test for the Provider model."""
import logging
from unittest.mock import call, patch
from uuid import UUID

from faker import Faker
from tenant_schemas.utils import tenant_context

from api.iam.models import Tenant
from api.provider.models import Provider
from masu.test import MasuTestCase

FAKE = Faker()


class ProviderModelTest(MasuTestCase):
    """Test case with pre-loaded data for the Provider model."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        if not getattr(cls, 'tenant', None):
            cls.tenant = Tenant.objects.get_or_create(schema_name=cls.schema)[0]

    @patch('masu.celery.tasks.delete_archived_data')
    def test_delete_single_provider_instance(self, mock_delete_archived_data):
        """Assert the delete_archived_data task is called upon instance delete."""
        with tenant_context(self.tenant):
            self.aws_provider.delete()
        mock_delete_archived_data.delay.assert_called_with(
            self.schema, Provider.PROVIDER_AWS, self.aws_provider_uuid
        )

    @patch('masu.celery.tasks.delete_archived_data')
    def test_delete_single_provider_skips_delete_archived_data_if_customer_is_none(
        self, mock_delete_archived_data
    ):
        """Assert the delete_archived_data task is not called if Customer is None."""
        # remove filters on logging
        logging.disable(logging.NOTSET)
        with tenant_context(self.tenant), self.assertLogs(
            'api.provider.provider_manager', 'WARNING'
        ) as captured_logs:
            self.aws_provider.customer = None
            self.aws_provider.delete()
        mock_delete_archived_data.delay.assert_not_called()
        self.assertIn('has no Customer', captured_logs.output[0])

        # restore filters on logging
        logging.disable(logging.CRITICAL)

    @patch('masu.celery.tasks.delete_archived_data')
    def test_delete_all_providers_from_queryset(self, mock_delete_archived_data):
        """Assert the delete_archived_data task is called upon queryset delete."""
        mock_delete_archived_data.reset_mock()
        with tenant_context(self.tenant):
            Provider.objects.all().delete()
        expected_calls = [
            call(self.schema, Provider.PROVIDER_AWS, UUID(self.aws_provider_uuid)),
            call(self.schema, Provider.PROVIDER_OCP, UUID(self.ocp_provider_uuid)),
            call(self.schema, Provider.PROVIDER_AZURE, UUID(self.azure_provider_uuid)),
        ]
        mock_delete_archived_data.delay.assert_has_calls(expected_calls, any_order=True)
