#
# Copyright 2020 Red Hat, Inc.
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
import logging
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.db import InterfaceError
from django.db.models.signals import post_save
from django.test import TestCase

from api.provider.models import Provider
from api.provider.models import Sources
from providers.provider_access import ProviderAccessor
from sources.config import Config
from sources.kafka_listener import storage_callback
from sources.sources_http_client import SourcesHTTPClientError
from sources.tasks import create_or_update_provider
from sources.tasks import delete_source_and_provider
from sources.tasks import set_status_for_source

AUTHENTICATIONS = {
    Provider.PROVIDER_AWS: {"resource_name": "arn:aws:iam::111111111111:role/CostManagement"},
    Provider.PROVIDER_AZURE: {
        "credentials": {
            "client_id": "11111111-2222-4444-8888-ffffffffffff",
            "tenant_id": "11111111-2222-4444-8888-ffffffffffff",
            "client_secret": "its actually a secret",
            "subscription_id": "11111111-2222-4444-8888-ffffffffffff",
        }
    },
}

BILLING_SOURCES = {
    Provider.PROVIDER_AWS: {"bucket": "test_bucket"},
    Provider.PROVIDER_AZURE: {
        "data_source": {"resource_group": "resource-group", "storage_account": "storage-account"}
    },
}


class MockStatus:
    """Mock class."""

    def __init__(self, *args):
        """Initialize the task."""
        self.id = uuid4()
        set_status_for_source(*args)


class SourcesTasksTest(TestCase):
    """Test cases for Sources Tasks."""

    def setUp(self):
        super().setUp()
        post_save.disconnect(storage_callback, sender=Sources)

        self.aws_source_info = {
            "source_id": 1,
            "source_uuid": uuid4(),
            "account_id": "acct12345",
            "offset": 1,
            "auth_header": Config.SOURCES_FAKE_HEADER,
            "name": "FakeAWS",
            "source_type": Provider.PROVIDER_AWS,
        }
        self.aws_source = Sources.objects.create(**self.aws_source_info)
        self.aws_source.save()

        self.azure_source_info = {
            "source_id": 2,
            "source_uuid": uuid4(),
            "account_id": "acct12345",
            "offset": 2,
            "auth_header": Config.SOURCES_FAKE_HEADER,
            "name": "FakeAzure",
            "source_type": Provider.PROVIDER_AZURE,
        }
        self.azure_source = Sources.objects.create(**self.azure_source_info)
        self.azure_source.save()

    @patch("masu.celery.tasks.check_report_updates")
    @patch("sources.tasks.set_status_for_source")
    def test_create_with_complete_source(self, mock_status, __):
        """Test that provider is created when source is complete and source status is saved."""
        self.aws_source.billing_source = BILLING_SOURCES.get(Provider.PROVIDER_AWS)
        self.aws_source.authentication = AUTHENTICATIONS.get(Provider.PROVIDER_AWS)
        self.aws_source.save()
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            create_or_update_provider(self.aws_source.source_id)
        self.assertTrue(Provider.objects.filter(uuid=self.aws_source.source_uuid).exists())
        source = Sources.objects.get(source_id=self.aws_source_info.get("source_id"))
        self.assertEqual(source.status.get("availability_status"), "available")

        self.azure_source.billing_source = BILLING_SOURCES.get(Provider.PROVIDER_AZURE)
        self.azure_source.authentication = AUTHENTICATIONS.get(Provider.PROVIDER_AZURE)
        self.azure_source.save()
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            create_or_update_provider(self.azure_source.source_id)
        self.assertTrue(Provider.objects.filter(uuid=self.azure_source.source_uuid).exists())
        source = Sources.objects.get(source_id=self.azure_source_info.get("source_id"))
        self.assertEqual(source.status.get("availability_status"), "available")

    def test_create_with_incomplete_source(self):
        """Test that provider is not created when source is incomplete."""
        create_or_update_provider(self.aws_source.source_id)
        self.assertFalse(Provider.objects.filter(uuid=self.aws_source.source_uuid).exists())

        create_or_update_provider(self.azure_source.source_id)
        self.assertFalse(Provider.objects.filter(uuid=self.azure_source.source_uuid).exists())

    def test_create_with_nonexistent_source(self):
        """Test that provider is not created when source is not real."""
        logging.disable(logging.NOTSET)
        with self.assertLogs(logger="sources.tasks", level="ERROR"):
            create_or_update_provider(3)

    @patch("masu.celery.tasks.check_report_updates")
    @patch("sources.tasks.set_status_for_source")
    def test_create_with_complete_source_validation_error(self, mock_status, __):
        """Test that provider is created when source is complete and source status is saved."""
        self.aws_source.billing_source = BILLING_SOURCES.get(Provider.PROVIDER_AWS)
        self.aws_source.authentication = AUTHENTICATIONS.get(Provider.PROVIDER_AWS)
        self.aws_source.save()
        logging.disable(logging.ERROR)
        create_or_update_provider(self.aws_source.source_id)
        self.assertFalse(Provider.objects.filter(uuid=self.aws_source.source_uuid).exists())
        source = Sources.objects.get(source_id=self.aws_source_info.get("source_id"))
        self.assertEqual(source.status.get("availability_status"), "unavailable")

    @patch.object(settings, "DEVELOPMENT", False)
    @patch("masu.celery.tasks.check_report_updates")
    @patch("sources.tasks.set_status_for_source.delay", side_effect=MockStatus)
    @patch("sources.sources_http_client.SourcesHTTPClient.set_source_status")
    def test_set_status(self, mock_call, mock_status, __):
        """Test that set status is called when source exists."""
        self.aws_source.billing_source = BILLING_SOURCES.get(Provider.PROVIDER_AWS)
        self.aws_source.authentication = AUTHENTICATIONS.get(Provider.PROVIDER_AWS)
        self.aws_source.save()
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            create_or_update_provider(self.aws_source.source_id)

        mock_call.assert_called()

    @patch.object(settings, "DEVELOPMENT", False)
    @patch("masu.celery.tasks.check_report_updates")
    @patch("sources.tasks.set_status_for_source.delay", side_effect=MockStatus)
    @patch(
        "sources.sources_http_client.SourcesHTTPClient.set_source_status",
        side_effect=SourcesHTTPClientError("mock-error"),
    )
    def test_set_status_error(self, mock_call, mock_status, __):
        """Test that set status is called when source exists."""
        self.aws_source.billing_source = BILLING_SOURCES.get(Provider.PROVIDER_AWS)
        self.aws_source.authentication = AUTHENTICATIONS.get(Provider.PROVIDER_AWS)
        self.aws_source.save()
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            with self.assertLogs("sources.tasks", level=logging.ERROR):
                create_or_update_provider(self.aws_source.source_id)

        mock_call.assert_called()

    @patch("sources.tasks.KafkaSourceManager.destroy_provider")
    def test_destroy_source_and_provider(self, mock_destory_provider):
        """Test that destroys source."""
        aws_source = Sources.objects.get(source_type="AWS")
        aws_provider = Provider.objects.get(type="AWS-local")

        # Associate models
        aws_source.source_uuid = aws_provider.uuid
        aws_source.koku_uuid = aws_provider.uuid
        aws_source.save()

        source_id = aws_source.source_id
        source_uuid = aws_source.source_uuid

        delete_source_and_provider(source_id, source_uuid, aws_source.auth_header)
        self.assertFalse(Sources.objects.filter(source_id=source_id).exists())
        mock_destory_provider.assert_called()

    @patch("sources.tasks.KafkaSourceManager.destroy_provider")
    def test_destroy_source_and_provider_no_provider(self, mock_destory_provider):
        """Test that destroys source with no provider."""
        aws_source = Sources.objects.get(source_type="AWS")
        aws_provider = Provider.objects.get(type="AWS-local")

        # Associate models
        aws_source.koku_uuid = aws_provider.uuid
        aws_source.save()

        source_id = aws_source.source_id
        source_uuid = uuid4()  # Use incorrect UUID to simulate no provider.

        delete_source_and_provider(source_id, source_uuid, aws_source.auth_header)
        self.assertFalse(Sources.objects.filter(source_id=source_id).exists())
        mock_destory_provider.assert_not_called()

    @patch("sources.tasks.KafkaSourceManager.destroy_provider", side_effect=Exception("test error"))
    def test_destroy_source_and_provider_exception(self, mock_destory_provider):
        """Test that destroys source with provider exception."""
        aws_source = Sources.objects.get(source_type="AWS")
        aws_provider = Provider.objects.get(type="AWS-local")

        # Associate models
        aws_source.source_uuid = aws_provider.uuid
        aws_source.koku_uuid = aws_provider.uuid
        aws_source.save()

        source_id = aws_source.source_id
        source_uuid = aws_source.source_uuid

        delete_source_and_provider(source_id, source_uuid, aws_source.auth_header)
        self.assertTrue(Sources.objects.filter(source_id=source_id).exists())

    @patch("sources.tasks.KafkaSourceManager.destroy_provider")
    def test_destroy_source_and_provider_source_does_not_exist(self, mock_destory_provider):
        """Test that destroys source where source does not exist."""
        aws_source = Sources.objects.get(source_type="AWS")
        aws_provider = Provider.objects.get(type="AWS-local")

        # Associate models
        aws_source.source_uuid = aws_provider.uuid
        aws_source.koku_uuid = aws_provider.uuid
        aws_source.save()

        non_existent_source_id = 1
        while Sources.objects.filter(source_id=non_existent_source_id).exists():
            non_existent_source_id += 1

        source_id = non_existent_source_id
        source_uuid = aws_source.source_uuid

        delete_source_and_provider(source_id, source_uuid, aws_source.auth_header)
        mock_destory_provider.assert_called()

    @patch("sources.tasks.destroy_source_event", side_effect=InterfaceError)
    @patch("sources.tasks.KafkaSourceManager.destroy_provider")
    def test_destroy_source_and_provider_source_db_errort(self, mock_destory_provider, mock_destroy_source):
        """Test that destroys source where database error occurs."""
        aws_source = Sources.objects.get(source_type="AWS")
        aws_provider = Provider.objects.get(type="AWS-local")

        # Associate models
        aws_source.source_uuid = aws_provider.uuid
        aws_source.koku_uuid = aws_provider.uuid
        aws_source.save()

        source_id = aws_source.source_id
        source_uuid = aws_source.source_uuid

        delete_source_and_provider(source_id, source_uuid, aws_source.auth_header)
        self.assertTrue(Sources.objects.filter(source_id=source_id).exists())
