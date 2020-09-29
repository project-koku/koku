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
from unittest.mock import call
from unittest.mock import patch
from uuid import UUID

from django.test.utils import override_settings
from django_tenants.utils import tenant_context
from faker import Faker

from api.provider.models import Provider
from cost_models.cost_model_manager import CostModelManager
from cost_models.models import CostModelMap
from masu.test import MasuTestCase

FAKE = Faker()


class ProviderModelTest(MasuTestCase):
    """Test case with pre-loaded data for the Provider model."""

    @override_settings(ENABLE_S3_ARCHIVING=True)
    @patch("api.provider.provider_manager.transaction.on_commit")
    @patch("masu.celery.tasks.delete_archived_data")
    def test_delete_single_provider_instance(self, mock_delete_archived_data, mock_commit):
        """Assert the delete_archived_data task is called upon instance delete."""
        mock_commit.side_effect = mock_delete_archived_data.delay(
            self.schema, Provider.PROVIDER_AWS, self.aws_provider_uuid
        )
        with tenant_context(self.tenant):
            self.aws_provider.delete()
        mock_delete_archived_data.delay.assert_called_with(self.schema, Provider.PROVIDER_AWS, self.aws_provider_uuid)

    @override_settings(ENABLE_S3_ARCHIVING=True)
    @patch("api.provider.provider_manager.transaction.on_commit")
    @patch("masu.celery.tasks.delete_archived_data")
    def test_delete_single_provider_with_cost_model(self, mock_delete_archived_data, mock_commit):
        """Assert the cost models are deleted upon provider instance delete."""
        mock_commit.side_effect = mock_delete_archived_data.delay(
            self.schema, Provider.PROVIDER_AWS, self.aws_provider_uuid
        )
        provider_uuid = self.aws_provider.uuid
        data = {
            "name": "Test Cost Model",
            "description": "Test",
            "rates": [],
            "markup": {"value": FAKE.pyint() % 100, "unit": "percent"},
            "provider_uuids": [provider_uuid],
        }
        with tenant_context(self.tenant):
            manager = CostModelManager()
            with patch("cost_models.cost_model_manager.chain"):
                manager.create(**data)
            cost_model_map = CostModelMap.objects.filter(provider_uuid=provider_uuid)
            self.assertIsNotNone(cost_model_map)
            self.aws_provider.delete()
            self.assertEquals(0, CostModelMap.objects.filter(provider_uuid=provider_uuid).count())
        mock_delete_archived_data.delay.assert_called_with(self.schema, Provider.PROVIDER_AWS, self.aws_provider_uuid)

    @patch("masu.celery.tasks.delete_archived_data")
    def test_delete_single_provider_no_archiving(self, mock_delete_archived_data):
        """Assert the delete_archived_data task is not called if archiving is not enabled."""
        with patch("api.provider.provider_manager.settings", ENABLE_S3_ARCHIVING=False):
            with tenant_context(self.tenant):
                self.aws_provider.delete()
        mock_delete_archived_data.delay.assert_not_called()

    @override_settings(ENABLE_S3_ARCHIVING=True)
    @patch("masu.celery.tasks.delete_archived_data")
    def test_delete_single_provider_skips_delete_archived_data_if_customer_is_none(self, mock_delete_archived_data):
        """Assert the delete_archived_data task is not called if Customer is None."""
        # remove filters on logging
        logging.disable(logging.NOTSET)
        with tenant_context(self.tenant), self.assertLogs("api.provider.provider_manager", "WARNING") as captured_logs:
            self.aws_provider.customer = None
            self.aws_provider.delete()
        mock_delete_archived_data.delay.assert_not_called()
        self.assertIn("has no Customer", captured_logs.output[0])

        # restore filters on logging
        logging.disable(logging.CRITICAL)

    @override_settings(ENABLE_S3_ARCHIVING=True)
    @patch("api.provider.provider_manager.transaction.on_commit")
    @patch("masu.celery.tasks.delete_archived_data")
    def test_delete_all_providers_from_queryset(self, mock_delete_archived_data, mock_commit):
        """Assert the delete_archived_data task is called upon queryset delete."""
        mock_delete_archived_data.reset_mock()
        with tenant_context(self.tenant):
            providers = Provider.objects.all()
            for provider in providers:
                mock_commit.side_effect = mock_delete_archived_data.delay(self.schema, provider.type, provider.uuid)
                provider.delete()
        expected_calls = [
            call(self.schema, Provider.PROVIDER_AWS_LOCAL, UUID(self.aws_provider_uuid)),
            call(self.schema, Provider.PROVIDER_OCP, UUID(self.ocp_provider_uuid)),
            call(self.schema, Provider.PROVIDER_AZURE_LOCAL, UUID(self.azure_provider_uuid)),
        ]
        mock_delete_archived_data.delay.assert_has_calls(expected_calls, any_order=True)
