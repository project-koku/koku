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

from django.db.models.signals import post_save
from django.test import TestCase

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
from sources.kafka_message_processor import SourceMsgProcessor
from sources.test.test_kafka_listener import ConsumerRecord
from sources.test.test_sources_http_client import COST_MGMT_APP_TYPE_ID

NoneType = type(None)


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


class KafkaMessageProcessorTest(TestCase):
    """Test cases for KafkaMessageProcessor."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        post_save.disconnect(storage_callback, sender=Sources)
        account = "12345"
        IdentityHeaderMiddleware.create_customer(account)

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
