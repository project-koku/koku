#
# Copyright 2021 Red Hat, Inc.
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
"""Test the Sources Kafka Listener handler."""
from uuid import uuid4

from django.db.models.signals import post_save
from django.test import TestCase
from django.test.utils import override_settings

from api.provider.models import Sources
from koku.middleware import IdentityHeaderMiddleware
from sources.config import Config
from sources.kafka_listener import storage_callback
from sources.tasks import delete_source
from sources.tasks import delete_source_beat


class SourcesTasksTest(TestCase):
    """Test Cases for the Sources Tasks."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        post_save.disconnect(storage_callback, sender=Sources)
        account = "12345"
        IdentityHeaderMiddleware.create_customer(account)

    def setUp(self):
        """Setup the test method."""
        super().setUp()
        self.aws_source = {
            "source_id": 10,
            "source_uuid": uuid4(),
            "name": "ProviderAWS",
            "source_type": "AWS",
            "authentication": {"credentials": {"role_arn": "arn:aws:iam::111111111111:role/CostManagement"}},
            "billing_source": {"data_source": {"bucket": "fake-bucket"}},
            "auth_header": Config.SOURCES_FAKE_HEADER,
            "account_id": "acct10001",
            "offset": 10,
            "pending_delete": True,
        }
        self.aws_local_source = {
            "source_id": 11,
            "source_uuid": uuid4(),
            "name": "ProviderAWS Local",
            "source_type": "AWS-local",
            "authentication": {"credentials": {"role_arn": "arn:aws:iam::111111111111:role/CostManagement"}},
            "billing_source": {"data_source": {"bucket": "fake-local-bucket"}},
            "auth_header": Config.SOURCES_FAKE_HEADER,
            "account_id": "acct10001",
            "offset": 11,
        }

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_execute_source_destroy_beat(self):
        """Test to execute the beat source delete."""
        source_id_aws = self.aws_source.get("source_id")
        source_id_local = self.aws_local_source.get("source_id")
        for s in (self.aws_source, self.aws_local_source):
            provider = Sources(**s)
            provider.save()

        delete_source_beat()

        self.assertEqual(Sources.objects.filter(source_id=source_id_aws).exists(), False)
        self.assertEqual(Sources.objects.filter(source_id=source_id_local).exists(), True)

    def test_execute_source_destroy_double_delete(self):
        """Test to execute source delete of same source."""
        source_id_aws = self.aws_source.get("source_id")
        source_id_local = self.aws_local_source.get("source_id")
        for s in (self.aws_source, self.aws_local_source):
            provider = Sources(**s)
            provider.save()

        delete_source(source_id_aws, self.aws_source.get("auth_header"), self.aws_source.get("source_uuid"))

        try:
            delete_source(source_id_aws, self.aws_source.get("auth_header"), self.aws_source.get("source_uuid"))
        except Exception as error:
            self.fail(f"test_execute_koku_provider_op_destroy test failure: {error}")

        self.assertEqual(Sources.objects.filter(source_id=source_id_aws).exists(), False)
        self.assertEqual(Sources.objects.filter(source_id=source_id_local).exists(), True)
