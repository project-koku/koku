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
import json
from unittest.mock import patch
from uuid import uuid4

from django.db.models.signals import post_save
from faker import Faker

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.models import Sources
from koku.middleware import IdentityHeaderMiddleware
from sources.config import Config
from sources.kafka_listener import storage_callback
from sources.kafka_message_processor import ApplicationMsgProcessor
from sources.kafka_message_processor import AuthenticationMsgProcessor
from sources.kafka_message_processor import create_msg_processor
from sources.kafka_message_processor import KAFKA_APPLICATION_CREATE
from sources.kafka_message_processor import KAFKA_APPLICATION_DESTROY
from sources.kafka_message_processor import KAFKA_APPLICATION_UPDATE
from sources.kafka_message_processor import KAFKA_AUTHENTICATION_CREATE
from sources.kafka_message_processor import KAFKA_AUTHENTICATION_UPDATE
from sources.kafka_message_processor import KAFKA_SOURCE_DESTROY
from sources.kafka_message_processor import KAFKA_SOURCE_UPDATE
from sources.kafka_message_processor import SourceDetails
from sources.kafka_message_processor import SourceMsgProcessor
from sources.kafka_message_processor import SOURCES_AWS_SOURCE_NAME
from sources.kafka_message_processor import SOURCES_AZURE_SOURCE_NAME
from sources.kafka_message_processor import SOURCES_GCP_SOURCE_NAME
from sources.kafka_message_processor import SOURCES_OCP_SOURCE_NAME
from sources.sources_http_client import SourcesHTTPClient
from sources.test.test_kafka_listener import ConsumerRecord
from sources.test.test_sources_http_client import COST_MGMT_APP_TYPE_ID

NoneType = type(None)

FAKER = Faker()
SOURCE_TYPE_IDS = {
    1: SOURCES_AWS_SOURCE_NAME,
    2: SOURCES_AZURE_SOURCE_NAME,
    3: SOURCES_GCP_SOURCE_NAME,
    4: SOURCES_OCP_SOURCE_NAME,
}
SOURCE_TYPE_IDS_MAP = {
    Provider.PROVIDER_AWS: 1,
    Provider.PROVIDER_AZURE: 2,
    Provider.PROVIDER_GCP: 3,
    Provider.PROVIDER_OCP: 4,
}


def msg_generator(event_type, topic=None, offset=None, value=None):
    test_value = '{"id":1,"source_id":1,"application_type_id":2}'
    if value:
        test_value = json.dumps(value)
    return ConsumerRecord(
        topic=topic or "platform.sources.event-stream",
        offset=offset or 5,
        event_type=event_type,
        auth_header=Config.SOURCES_FAKE_HEADER,
        value=bytes(test_value, encoding="utf-8"),
    )


def mock_details_generator(provider_type, name, uid, source_id):
    """Generates a fake source details dict."""
    source_type_id = SOURCE_TYPE_IDS_MAP[provider_type]
    details = {"name": name, "source_type_id": source_type_id, "uid": uid}
    with patch.object(SourcesHTTPClient, "get_source_details", return_value=details):
        with patch.object(SourcesHTTPClient, "get_source_type_name", return_value=SOURCE_TYPE_IDS[source_type_id]):
            return SourceDetails(Config.SOURCES_FAKE_HEADER, source_id)


class KafkaMessageProcessorTest(IamTestCase):
    """Test cases for KafkaMessageProcessor."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        post_save.disconnect(storage_callback, sender=Sources)
        account = "12345"
        IdentityHeaderMiddleware.create_customer(account)

    def test_fake_details_generator(self):
        """Test to ensure the generator makes things correctly."""
        provider_types = [Provider.PROVIDER_AWS, Provider.PROVIDER_AZURE, Provider.PROVIDER_GCP, Provider.PROVIDER_OCP]
        for provider in provider_types:
            with self.subTest(test=provider):
                uid = uuid4()
                name = FAKER.name()
                source_id = FAKER.pyint()
                deets = mock_details_generator(provider, name, uid, source_id)
                self.assertIsInstance(deets, SourceDetails)
                self.assertEqual(deets.name, name)
                self.assertEqual(deets.source_type, provider)
                self.assertEqual(deets.source_type_name, SOURCE_TYPE_IDS[SOURCE_TYPE_IDS_MAP[provider]])
                self.assertEqual(deets.source_uuid, uid)

    def test_create_msg_processor(self):
        """Test create_msg_processor returns the correct processor based on msg event."""
        test_mtx = [
            {"event_type": KAFKA_APPLICATION_CREATE, "expected": ApplicationMsgProcessor},
            {"event_type": KAFKA_APPLICATION_UPDATE, "expected": ApplicationMsgProcessor},
            {"event_type": KAFKA_APPLICATION_DESTROY, "expected": ApplicationMsgProcessor},
            {"event_type": KAFKA_AUTHENTICATION_CREATE, "expected": AuthenticationMsgProcessor},
            {"event_type": KAFKA_AUTHENTICATION_UPDATE, "expected": AuthenticationMsgProcessor},
            {
                "event_type": KAFKA_SOURCE_UPDATE,
                "expected": NoneType,
            },  # maybe someday we will listen to source.update messages
            {"event_type": KAFKA_SOURCE_DESTROY, "expected": SourceMsgProcessor},
            {"event_type": "Source.create", "expected": NoneType},
            {"event_type": KAFKA_SOURCE_DESTROY, "test_topic": "unknown", "expected": NoneType},
        ]

        for test in test_mtx:
            with self.subTest(test=test):
                msg = msg_generator(event_type=test.get("event_type"), topic=test.get("test_topic"))
                self.assertIsInstance(create_msg_processor(msg, COST_MGMT_APP_TYPE_ID), test.get("expected"))

    def test_create_msg_processor_missing_header(self):
        """Test create_msg_processor on a message missing kafka headers."""
        msg = msg_generator(event_type=KAFKA_SOURCE_DESTROY)
        msg._headers = {}  # override the generator headers
        self.assertIsInstance(create_msg_processor(msg, COST_MGMT_APP_TYPE_ID), NoneType)
