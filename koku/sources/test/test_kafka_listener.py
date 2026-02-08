#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Sources Kafka Listener handler."""
import queue
from random import choice
from unittest.mock import patch
from uuid import uuid4

import requests_mock
from confluent_kafka import KafkaError
from confluent_kafka import KafkaException
from django.db import IntegrityError
from django.db import InterfaceError
from django.db import OperationalError
from django.db.models.signals import post_save
from django.forms.models import model_to_dict
from django.test.utils import override_settings
from faker import Faker
from rest_framework.exceptions import ValidationError

import sources.kafka_listener as source_integration
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.models import Sources
from api.provider.provider_builder import ProviderBuilder
from api.provider.provider_builder import ProviderBuilderError
from koku.middleware import IdentityHeaderMiddleware
from providers.provider_access import ProviderAccessor
from providers.provider_errors import SkipStatusPush
from sources import storage
from sources.config import Config
from sources.kafka_listener import PROCESS_QUEUE
from sources.kafka_listener import process_synchronize_sources_msg
from sources.kafka_listener import SourcesIntegrationError
from sources.kafka_listener import storage_callback
from sources.kafka_message_processor import ApplicationMsgProcessor
from sources.kafka_message_processor import AUTH_TYPES
from sources.kafka_message_processor import AuthenticationMsgProcessor
from sources.kafka_message_processor import KAFKA_APPLICATION_CREATE
from sources.kafka_message_processor import KAFKA_APPLICATION_DESTROY
from sources.kafka_message_processor import KAFKA_APPLICATION_PAUSE
from sources.kafka_message_processor import KAFKA_APPLICATION_UNPAUSE
from sources.kafka_message_processor import KAFKA_APPLICATION_UPDATE
from sources.kafka_message_processor import KAFKA_AUTHENTICATION_CREATE
from sources.kafka_message_processor import KAFKA_AUTHENTICATION_UPDATE
from sources.kafka_message_processor import KAFKA_SOURCE_DESTROY
from sources.kafka_message_processor import KAFKA_SOURCE_UPDATE
from sources.sources_http_client import ENDPOINT_APPLICATION_TYPES
from sources.sources_http_client import ENDPOINT_APPLICATIONS
from sources.sources_http_client import ENDPOINT_AUTHENTICATIONS
from sources.sources_http_client import ENDPOINT_SOURCE_TYPES
from sources.sources_http_client import ENDPOINT_SOURCES
from sources.sources_http_client import SourcesHTTPClient
from sources.sources_provider_coordinator import SourcesProviderCoordinator
from sources.test.test_kafka_message_processor import msg_generator
from sources.test.test_kafka_message_processor import SOURCE_TYPE_IDS
from sources.test.test_kafka_message_processor import SOURCE_TYPE_IDS_MAP
from sources.test.test_sources_http_client import COST_MGMT_APP_TYPE_ID
from sources.test.test_sources_http_client import MOCK_PREFIX
from sources.test.test_sources_http_client import MOCK_URL

faker = Faker()
FAKE_AWS_ARN = "arn:aws:iam::111111111111:role/CostManagement"
FAKE_EXTERNAL_ID = str(uuid4())
FAKE_AWS_ARN2 = "arn:aws:iam::22222222222:role/CostManagement"
FAKE_CLUSTER_ID_1 = str(uuid4())
FAKE_CLUSTER_ID_2 = str(uuid4())
SOURCES_APPS = (
    "http://www.sources.com/api/sources/v1.0/applications?filter[application_type_id]={}&filter[source_id]={}"
)


def raise_source_manager_error(param_a, param_b, param_c, param_d, param_e):
    """Raise ProviderBuilderError"""
    raise ProviderBuilderError()


def raise_validation_error(param_a, param_b, param_c, param_d, param_e):
    """Raise ValidationError"""
    raise ValidationError()


def raise_provider_manager_error(*args, **kwargs):
    """Raise ProviderBuilderError"""
    raise ProviderBuilderError("test exception")


class MockKafkaConsumer:
    def __init__(self, preloaded_messages=["hi", "world"]):
        self.preloaded_messages = preloaded_messages

    def start(self):
        pass

    def stop(self):
        pass

    def commit(self):
        self.preloaded_messages.pop()

    def seek(self, topic_partition):
        return

    def getone(self):
        for msg in self.preloaded_messages:
            return msg
        raise KafkaException(KafkaError._PARTITION_EOF)

    def __aiter__(self):
        return self

    def __anext__(self):
        return self.getone()


@patch.object(Config, "SOURCES_API_URL", MOCK_URL)
class SourcesKafkaMsgHandlerTest(IamTestCase):
    """Test Cases for the Sources Kafka Listener."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        post_save.disconnect(storage_callback, sender=Sources)
        account = "10001"
        org_id = "1234567"
        IdentityHeaderMiddleware.create_customer(account, org_id, "POST")

    def setUp(self):
        """Setup the test method."""
        super().setUp()
        self.aws_local_source = {
            "source_id": 11,
            "source_uuid": uuid4(),
            "name": "ProviderAWS Local",
            "source_type": "AWS-local",
            "authentication": {"credentials": {"role_arn": "arn:aws:iam::111111111111:role/CostManagement"}},
            "billing_source": {"data_source": {"bucket": "fake-local-bucket"}},
            "auth_header": Config.SOURCES_FAKE_HEADER,
            "account_id": "org1234567",
            "org_id": "1234567",
            "offset": 11,
        }
        self.uuids = {
            Provider.PROVIDER_AWS: uuid4(),
            # Provider.PROVIDER_AZURE: uuid4(),
            # Provider.PROVIDER_GCP: uuid4(),
            Provider.PROVIDER_OCP: uuid4(),
        }
        self.source_ids = {
            Provider.PROVIDER_AWS: 10,
            # Provider.PROVIDER_AZURE: 11,
            # Provider.PROVIDER_GCP: 12,
            Provider.PROVIDER_OCP: 13,
        }
        self.sources = {
            Provider.PROVIDER_AWS: {
                "source_id": self.source_ids.get(Provider.PROVIDER_AWS),
                "source_uuid": self.uuids.get(Provider.PROVIDER_AWS),
                "name": "Provider AWS",
                "source_type": "AWS",
                "authentication": {"credentials": {"role_arn": FAKE_AWS_ARN, "external_id": FAKE_EXTERNAL_ID}},
                "billing_source": {"data_source": {"bucket": "test_bucket"}},
                "auth_header": Config.SOURCES_FAKE_HEADER,
                "account_id": "10001",
                "org_id": "1234567",
                "offset": 5,
            },
            Provider.PROVIDER_OCP: {
                "source_id": self.source_ids.get(Provider.PROVIDER_OCP),
                "source_uuid": self.uuids.get(Provider.PROVIDER_OCP),
                "name": "Provider OCP",
                "source_type": "OCP",
                "authentication": {"credentials": {"cluster_id": FAKE_CLUSTER_ID_1}},
                "auth_header": Config.SOURCES_FAKE_HEADER,
                "account_id": "10001",
                "org_id": "1234567",
                "offset": 5,
            },
        }
        self.updated_sources = {
            Provider.PROVIDER_AWS: {
                "source_id": self.source_ids.get(Provider.PROVIDER_AWS),
                "source_uuid": self.uuids.get(Provider.PROVIDER_AWS),
                "name": "Provider AWS - PATCHED",
                "source_type": "AWS",
                "authentication": {"credentials": {"role_arn": FAKE_AWS_ARN2, "external_id": FAKE_EXTERNAL_ID}},
                "billing_source": {"data_source": {"bucket": "test_bucket_2"}},
                "auth_header": Config.SOURCES_FAKE_HEADER,
                "account_id": "10001",
                "org_id": "1234567",
                "offset": 5,
            },
            Provider.PROVIDER_OCP: {
                "source_id": self.source_ids.get(Provider.PROVIDER_OCP),
                "source_uuid": self.uuids.get(Provider.PROVIDER_OCP),
                "name": "Provider OCP - PATCHED",
                "source_type": "OCP",
                "authentication": {"credentials": {"cluster_id": FAKE_CLUSTER_ID_2}},
                "auth_header": Config.SOURCES_FAKE_HEADER,
                "account_id": "10001",
                "org_id": "1234567",
                "offset": 5,
            },
        }
        self.mock_create_requests = {
            Provider.PROVIDER_AWS: [
                {
                    "url": f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_APPLICATION_TYPES}/{COST_MGMT_APP_TYPE_ID}/sources?filter[id]={self.source_ids.get(Provider.PROVIDER_AWS)}",  # noqa: E501
                    "status": 200,
                    "json": {"data": [{"not": "empty"}]},
                },
                {
                    "url": f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_SOURCE_TYPES}?filter[id]={SOURCE_TYPE_IDS_MAP.get(Provider.PROVIDER_AWS)}",  # noqa: E501
                    "status": 200,
                    "json": {"data": [{"name": SOURCE_TYPE_IDS[SOURCE_TYPE_IDS_MAP[Provider.PROVIDER_AWS]]}]},
                },
                {
                    "url": f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_APPLICATIONS}?filter[source_id]={self.source_ids.get(Provider.PROVIDER_AWS)}",  # noqa: E501
                    "status": 200,
                    "json": {"data": [{"extra": {"bucket": "test_bucket"}}]},
                },
                {
                    "url": f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_AUTHENTICATIONS}?filter[source_id]={self.source_ids.get(Provider.PROVIDER_AWS)}",  # noqa: E501
                    "status": 200,
                    "json": {
                        "data": [
                            {
                                "id": self.source_ids.get(Provider.PROVIDER_AWS),
                                "username": FAKE_AWS_ARN,
                                "extra": {"external_id": FAKE_EXTERNAL_ID},
                            }
                        ]
                    },
                },
                {
                    "url": f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_SOURCES}/{self.source_ids.get(Provider.PROVIDER_AWS)}",  # noqa: E501
                    "status": 200,
                    "json": {
                        "name": "Provider AWS",
                        "source_type_id": SOURCE_TYPE_IDS_MAP.get(Provider.PROVIDER_AWS),
                        "uid": str(self.uuids.get(Provider.PROVIDER_AWS)),
                    },
                },
            ],
            Provider.PROVIDER_OCP: [
                {
                    "url": f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_APPLICATION_TYPES}/{COST_MGMT_APP_TYPE_ID}/sources?filter[id]={self.source_ids.get(Provider.PROVIDER_OCP)}",  # noqa: E501
                    "status": 200,
                    "json": {"data": [{"not": "empty"}]},
                },
                {
                    "url": f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_SOURCE_TYPES}?filter[id]={SOURCE_TYPE_IDS_MAP.get(Provider.PROVIDER_OCP)}",  # noqa: E501
                    "status": 200,
                    "json": {"data": [{"name": SOURCE_TYPE_IDS[SOURCE_TYPE_IDS_MAP[Provider.PROVIDER_OCP]]}]},
                },
                {
                    "url": f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_SOURCES}/{self.source_ids.get(Provider.PROVIDER_OCP)}",  # noqa: E501
                    "status": 200,
                    "json": {
                        "name": "Provider OCP",
                        "source_ref": FAKE_CLUSTER_ID_1,
                        "source_type_id": SOURCE_TYPE_IDS_MAP.get(Provider.PROVIDER_OCP),
                        "uid": str(self.uuids.get(Provider.PROVIDER_OCP)),
                    },
                },
            ],
        }
        self.mock_update_requests = {
            Provider.PROVIDER_AWS: [
                {
                    "url": f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_APPLICATION_TYPES}/{COST_MGMT_APP_TYPE_ID}/sources?filter[id]={self.source_ids.get(Provider.PROVIDER_AWS)}",  # noqa: E501
                    "status": 200,
                    "json": {"data": [{"not": "empty"}]},
                },
                {
                    "url": f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_SOURCE_TYPES}?filter[id]={SOURCE_TYPE_IDS_MAP.get(Provider.PROVIDER_AWS)}",  # noqa: E501
                    "status": 200,
                    "json": {"data": [{"name": SOURCE_TYPE_IDS[SOURCE_TYPE_IDS_MAP[Provider.PROVIDER_AWS]]}]},
                },
                {
                    "url": f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_APPLICATIONS}?filter[source_id]={self.source_ids.get(Provider.PROVIDER_AWS)}",  # noqa: E501
                    "status": 200,
                    "json": {"data": [{"extra": {"bucket": "test_bucket_2"}}]},
                },
                {
                    "url": f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_AUTHENTICATIONS}?filter[source_id]={self.source_ids.get(Provider.PROVIDER_AWS)}",  # noqa: E501
                    "status": 200,
                    "json": {
                        "data": [
                            {
                                "id": self.source_ids.get(Provider.PROVIDER_AWS),
                                "username": FAKE_AWS_ARN2,
                                "extra": {"external_id": FAKE_EXTERNAL_ID},
                            }
                        ]
                    },
                },
                {
                    "url": f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_SOURCES}/{self.source_ids.get(Provider.PROVIDER_AWS)}",  # noqa: E501
                    "status": 200,
                    "json": {
                        "name": "Provider AWS - PATCHED",
                        "source_type_id": SOURCE_TYPE_IDS_MAP.get(Provider.PROVIDER_AWS),
                        "uid": str(self.uuids.get(Provider.PROVIDER_AWS)),
                    },
                },
            ],
            Provider.PROVIDER_OCP: [
                {
                    "url": f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_APPLICATION_TYPES}/{COST_MGMT_APP_TYPE_ID}/sources?filter[id]={self.source_ids.get(Provider.PROVIDER_OCP)}",  # noqa: E501
                    "status": 200,
                    "json": {"data": [{"not": "empty"}]},
                },
                {
                    "url": f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_SOURCE_TYPES}?filter[id]={SOURCE_TYPE_IDS_MAP.get(Provider.PROVIDER_OCP)}",  # noqa: E501
                    "status": 200,
                    "json": {"data": [{"name": SOURCE_TYPE_IDS[SOURCE_TYPE_IDS_MAP[Provider.PROVIDER_OCP]]}]},
                },
                {
                    "url": f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_SOURCES}/{self.source_ids.get(Provider.PROVIDER_OCP)}",  # noqa: E501
                    "status": 200,
                    "json": {
                        "name": "Provider OCP - PATCHED",
                        "source_ref": FAKE_CLUSTER_ID_2,
                        "source_type_id": SOURCE_TYPE_IDS_MAP.get(Provider.PROVIDER_OCP),
                        "uid": str(self.uuids.get(Provider.PROVIDER_OCP)),
                    },
                },
            ],
        }
        self.mock_delete_requests = {
            Provider.PROVIDER_AWS: [
                {
                    "url": f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_SOURCES}/{self.source_ids.get(Provider.PROVIDER_AWS)}",  # noqa: E501
                    "status": 404,
                    "json": {"data": [{"not": "source not found"}]},
                },
            ],
            Provider.PROVIDER_OCP: [
                {
                    "url": f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_SOURCES}/{self.source_ids.get(Provider.PROVIDER_OCP)}",  # noqa: E501
                    "status": 404,
                    "json": {"data": [{"not": "source not found"}]},
                },
            ],
        }

    def test_listen_for_messages_create_update_pause_unpause_delete_AWS(self):
        """Test for app/auth create, app/auth update, app pause/unpause, app/source delete."""
        # First, test the create pathway:
        msgs = [
            msg_generator(
                KAFKA_APPLICATION_CREATE,
                value={
                    "id": 1,
                    "source_id": self.source_ids.get(Provider.PROVIDER_AWS),
                    "application_type_id": COST_MGMT_APP_TYPE_ID,
                },
            ),
            msg_generator(
                KAFKA_AUTHENTICATION_CREATE,
                value={
                    "id": 1,
                    "source_id": self.source_ids.get(Provider.PROVIDER_AWS),
                    "authtype": AUTH_TYPES.get(Provider.PROVIDER_AWS),
                },
            ),
        ]
        with requests_mock.mock() as m:
            for resp in self.mock_create_requests.get(Provider.PROVIDER_AWS):
                m.get(url=resp.get("url"), status_code=resp.get("status"), json=resp.get("json"))
            for msg in msgs:
                mock_consumer = MockKafkaConsumer([msg])
                source_integration.listen_for_messages(msg, mock_consumer, COST_MGMT_APP_TYPE_ID)
            source = Sources.objects.get(source_id=self.source_ids.get(Provider.PROVIDER_AWS))
            s = model_to_dict(source, fields=list(self.sources.get(Provider.PROVIDER_AWS).keys()))
            self.assertDictEqual(s, self.sources.get(Provider.PROVIDER_AWS), msg="failed create")

        # now test the update pathway
        msgs = [
            msg_generator(KAFKA_SOURCE_UPDATE, value={"id": self.source_ids.get(Provider.PROVIDER_AWS)}),
            # duplicate the message to test the `not updated` pathway
            msg_generator(KAFKA_SOURCE_UPDATE, value={"id": self.source_ids.get(Provider.PROVIDER_AWS)}),
            msg_generator(
                KAFKA_APPLICATION_UPDATE,
                value={
                    "id": 1,
                    "source_id": self.source_ids.get(Provider.PROVIDER_AWS),
                    "application_type_id": COST_MGMT_APP_TYPE_ID,
                },
            ),
            msg_generator(
                KAFKA_AUTHENTICATION_UPDATE,
                value={
                    "id": 1,
                    "source_id": self.source_ids.get(Provider.PROVIDER_AWS),
                    "authtype": AUTH_TYPES.get(Provider.PROVIDER_AWS),
                },
            ),
        ]
        with requests_mock.mock() as m:
            for resp in self.mock_update_requests.get(Provider.PROVIDER_AWS):
                m.get(url=resp.get("url"), status_code=resp.get("status"), json=resp.get("json"))
            for msg in msgs:
                mock_consumer = MockKafkaConsumer([msg])
                source_integration.listen_for_messages(msg, mock_consumer, COST_MGMT_APP_TYPE_ID)
            source = Sources.objects.get(source_id=self.source_ids.get(Provider.PROVIDER_AWS))
            s = model_to_dict(source, fields=list(self.updated_sources.get(Provider.PROVIDER_AWS).keys()))
            self.assertDictEqual(s, self.updated_sources.get(Provider.PROVIDER_AWS), msg="failed update")

        # now test pause/unpause pathway
        msgs = {
            KAFKA_APPLICATION_PAUSE: msg_generator(
                KAFKA_APPLICATION_PAUSE,
                value={
                    "id": 1,
                    "source_id": self.source_ids.get(Provider.PROVIDER_AWS),
                    "application_type_id": COST_MGMT_APP_TYPE_ID,
                },
            ),
            KAFKA_APPLICATION_UNPAUSE: msg_generator(
                KAFKA_APPLICATION_UNPAUSE,
                value={
                    "id": 1,
                    "source_id": self.source_ids.get(Provider.PROVIDER_AWS),
                    "application_type_id": COST_MGMT_APP_TYPE_ID,
                },
            ),
        }

        with requests_mock.mock() as m:
            for resp in self.mock_update_requests.get(Provider.PROVIDER_AWS):
                m.get(url=resp.get("url"), status_code=resp.get("status"), json=resp.get("json"))
            for event, msg in msgs.items():
                mock_consumer = MockKafkaConsumer([msg])
                source_integration.listen_for_messages(msg, mock_consumer, COST_MGMT_APP_TYPE_ID)
                source = Sources.objects.get(source_id=self.source_ids.get(Provider.PROVIDER_AWS))
                self.assertEqual(source.paused, event == KAFKA_APPLICATION_PAUSE, msg="failed pause/unpause")

        # now test the delete pathway
        msgs = [
            msg_generator(
                KAFKA_APPLICATION_DESTROY,
                value={
                    "id": 1,
                    "source_id": self.source_ids.get(Provider.PROVIDER_AWS),
                    "application_type_id": COST_MGMT_APP_TYPE_ID,
                },
            ),
            msg_generator(
                KAFKA_SOURCE_DESTROY,
                value={
                    "id": 1,
                    "source_id": self.source_ids.get(Provider.PROVIDER_AWS),
                    "application_type_id": COST_MGMT_APP_TYPE_ID,
                },
            ),
        ]
        with requests_mock.mock() as m:
            for resp in self.mock_delete_requests.get(Provider.PROVIDER_AWS):
                m.get(url=resp.get("url"), status_code=resp.get("status"), json=resp.get("json"))
            for msg in msgs:
                mock_consumer = MockKafkaConsumer([msg])
                source_integration.listen_for_messages(msg, mock_consumer, COST_MGMT_APP_TYPE_ID)
                source = Sources.objects.get(source_id=self.source_ids.get(Provider.PROVIDER_AWS))
                self.assertTrue(source.pending_delete, msg="failed delete")

    def test_listen_for_messages_create_update_pause_unpause_delete_OCP(self):
        """Test for app/auth create, app/auth update, app pause/unpause, app/source delete."""
        # First, test the create pathway:
        msgs = [
            msg_generator(
                KAFKA_APPLICATION_CREATE,
                value={
                    "id": 1,
                    "source_id": self.source_ids.get(Provider.PROVIDER_OCP),
                    "application_type_id": COST_MGMT_APP_TYPE_ID,
                },
            )
        ]
        with requests_mock.mock() as m:
            for resp in self.mock_create_requests.get(Provider.PROVIDER_OCP):
                m.get(url=resp.get("url"), status_code=resp.get("status"), json=resp.get("json"))
            for msg in msgs:
                mock_consumer = MockKafkaConsumer([msg])
                source_integration.listen_for_messages(msg, mock_consumer, COST_MGMT_APP_TYPE_ID)
            source = Sources.objects.get(source_id=self.source_ids.get(Provider.PROVIDER_OCP))
            s = model_to_dict(source, fields=list(self.sources.get(Provider.PROVIDER_OCP).keys()))
            self.assertDictEqual(s, self.sources.get(Provider.PROVIDER_OCP), msg="failed create")

        # now test the update pathway
        msgs = [
            msg_generator(KAFKA_SOURCE_UPDATE, value={"id": self.source_ids.get(Provider.PROVIDER_OCP)}),
            # duplicate the message to test the `not updated` pathway
            msg_generator(KAFKA_SOURCE_UPDATE, value={"id": self.source_ids.get(Provider.PROVIDER_OCP)}),
            msg_generator(
                KAFKA_APPLICATION_UPDATE,
                value={
                    "id": 1,
                    "source_id": self.source_ids.get(Provider.PROVIDER_OCP),
                    "application_type_id": COST_MGMT_APP_TYPE_ID,
                },
            ),
        ]
        with requests_mock.mock() as m:
            for resp in self.mock_update_requests.get(Provider.PROVIDER_OCP):
                m.get(url=resp.get("url"), status_code=resp.get("status"), json=resp.get("json"))
            for msg in msgs:
                mock_consumer = MockKafkaConsumer([msg])
                source_integration.listen_for_messages(msg, mock_consumer, COST_MGMT_APP_TYPE_ID)
            source = Sources.objects.get(source_id=self.source_ids.get(Provider.PROVIDER_OCP))
            s = model_to_dict(source, fields=list(self.updated_sources.get(Provider.PROVIDER_OCP).keys()))
            self.assertDictEqual(s, self.updated_sources.get(Provider.PROVIDER_OCP), msg="failed update")

        # now test pause/unpause pathway
        msgs = {
            KAFKA_APPLICATION_PAUSE: msg_generator(
                KAFKA_APPLICATION_PAUSE,
                value={
                    "id": 1,
                    "source_id": self.source_ids.get(Provider.PROVIDER_OCP),
                    "application_type_id": COST_MGMT_APP_TYPE_ID,
                },
            ),
            KAFKA_APPLICATION_UNPAUSE: msg_generator(
                KAFKA_APPLICATION_UNPAUSE,
                value={
                    "id": 1,
                    "source_id": self.source_ids.get(Provider.PROVIDER_OCP),
                    "application_type_id": COST_MGMT_APP_TYPE_ID,
                },
            ),
        }

        with requests_mock.mock() as m:
            for resp in self.mock_update_requests.get(Provider.PROVIDER_OCP):
                m.get(url=resp.get("url"), status_code=resp.get("status"), json=resp.get("json"))
            for event, msg in msgs.items():
                mock_consumer = MockKafkaConsumer([msg])
                source_integration.listen_for_messages(msg, mock_consumer, COST_MGMT_APP_TYPE_ID)
                source = Sources.objects.get(source_id=self.source_ids.get(Provider.PROVIDER_OCP))
                self.assertEqual(source.paused, event == KAFKA_APPLICATION_PAUSE, msg="failed pause/unpause")

        # now test the delete pathway
        msgs = [
            msg_generator(
                KAFKA_APPLICATION_DESTROY,
                value={
                    "id": 1,
                    "source_id": self.source_ids.get(Provider.PROVIDER_OCP),
                    "application_type_id": COST_MGMT_APP_TYPE_ID,
                },
            ),
            msg_generator(
                KAFKA_SOURCE_DESTROY,
                value={
                    "id": 1,
                    "source_id": self.source_ids.get(Provider.PROVIDER_OCP),
                    "application_type_id": COST_MGMT_APP_TYPE_ID,
                },
            ),
        ]
        with requests_mock.mock() as m:
            for resp in self.mock_delete_requests.get(Provider.PROVIDER_OCP):
                m.get(url=resp.get("url"), status_code=resp.get("status"), json=resp.get("json"))
            for msg in msgs:
                mock_consumer = MockKafkaConsumer([msg])
                source_integration.listen_for_messages(msg, mock_consumer, COST_MGMT_APP_TYPE_ID)
                source = Sources.objects.get(source_id=self.source_ids.get(Provider.PROVIDER_OCP))
                self.assertTrue(source.pending_delete, msg="failed delete")

    def test_message_not_associated_with_cost_mgmt(self):
        """Test that messages not associated with cost-mgmt are not processed."""
        table = [
            {"processor": ApplicationMsgProcessor, "event": KAFKA_APPLICATION_CREATE},
            {"processor": ApplicationMsgProcessor, "event": KAFKA_APPLICATION_UPDATE},
            {"processor": ApplicationMsgProcessor, "event": KAFKA_APPLICATION_DESTROY},
            {"processor": ApplicationMsgProcessor, "event": KAFKA_APPLICATION_PAUSE},
            {"processor": ApplicationMsgProcessor, "event": KAFKA_APPLICATION_UNPAUSE},
            {"processor": AuthenticationMsgProcessor, "event": KAFKA_AUTHENTICATION_CREATE},
            {"processor": AuthenticationMsgProcessor, "event": KAFKA_AUTHENTICATION_UPDATE},
        ]
        for test in table:
            with self.subTest(test=test):
                with requests_mock.mock() as m:
                    m.get(
                        url=f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_APPLICATION_TYPES}/{COST_MGMT_APP_TYPE_ID}/sources?filter[id]=1",  # noqa: E501
                        status_code=200,
                        json={"data": []},
                    )
                    with patch.object(test.get("processor"), "process") as mock_processor:
                        msg = msg_generator(
                            event_type=test.get("event"),
                            value={"id": 1, "source_id": 1, "application_type_id": COST_MGMT_APP_TYPE_ID + 1},
                        )
                        mock_consumer = MockKafkaConsumer([msg])
                        source_integration.listen_for_messages(msg, mock_consumer, COST_MGMT_APP_TYPE_ID)
                        mock_processor.assert_not_called()

    def test_listen_for_messages_exceptions_no_retry(self):
        """Test listen_for_messages exceptions that do not cause a retry."""
        table = [
            {"event": KAFKA_APPLICATION_CREATE, "header": True, "value": b'{"this value is messeged up}'},
            {"event": KAFKA_APPLICATION_DESTROY, "header": False},
            {"event": KAFKA_AUTHENTICATION_CREATE, "header": True},
        ]
        for test in table:
            with self.subTest(test=test):
                with requests_mock.mock() as m:
                    m.get(
                        url=f"{MOCK_URL}/{MOCK_PREFIX}/{ENDPOINT_APPLICATION_TYPES}/{COST_MGMT_APP_TYPE_ID}/sources?filter[id]=1",  # noqa: E501
                        status_code=404,
                        json={},
                    )
                    msg = msg_generator(test.get("event"))
                    if not test.get("header"):
                        msg = msg_generator(test.get("event"), header=None)
                    if test.get("value"):
                        msg._value = test.get("value")
                    mock_consumer = MockKafkaConsumer([msg])
                    with patch("sources.kafka_listener.time.sleep") as mock_time:
                        with patch.object(MockKafkaConsumer, "commit") as mocked_mock_consumer:
                            source_integration.listen_for_messages(msg, mock_consumer, COST_MGMT_APP_TYPE_ID)
                            mocked_mock_consumer.assert_called()
                            mock_time.assert_not_called()

    def test_listen_for_messages_http_exception(self):
        """Test listen_for_messages exceptions that cause a retry (http errors)."""
        table = [KAFKA_AUTHENTICATION_CREATE, KAFKA_AUTHENTICATION_UPDATE]
        for test in table:
            with self.subTest(test=test):
                with requests_mock.mock() as m:
                    for resp in self.mock_create_requests.get(Provider.PROVIDER_AWS):
                        m.get(url=resp.get("url"), status_code=401, json=resp.get("json"))
                    msg = msg_generator(
                        test,
                        value={
                            "id": 1,
                            "source_id": self.source_ids.get(Provider.PROVIDER_AWS),
                            "application_type_id": COST_MGMT_APP_TYPE_ID,
                            "authtype": choice(list(AUTH_TYPES.values())),
                        },
                    )
                    mock_consumer = MockKafkaConsumer([msg])
                    with patch("sources.kafka_listener.time.sleep") as mock_time:
                        source_integration.listen_for_messages(msg, mock_consumer, COST_MGMT_APP_TYPE_ID)
                        mock_time.assert_called()

    def test_listen_for_messages_exceptions_db_errors(self):
        """Test listen_for_messages exceptions that cause a retry (db errors)."""
        table = [
            {
                "event": KAFKA_APPLICATION_CREATE,
                "exception": InterfaceError,
                "path": "sources.storage.create_source_event",
            },
            {
                "event": KAFKA_AUTHENTICATION_CREATE,
                "exception": OperationalError,
                "path": "sources.storage.create_source_event",
            },
            {
                "event": KAFKA_APPLICATION_DESTROY,
                "exception": IntegrityError,
                "path": "sources.storage.enqueue_source_delete",
            },
        ]
        for test in table:
            with self.subTest(test=test):
                with requests_mock.mock() as m:
                    for resp in self.mock_create_requests.get(Provider.PROVIDER_AWS):
                        m.get(url=resp.get("url"), status_code=resp.get("status"), json=resp.get("json"))
                    msg = msg_generator(
                        test.get("event"),
                        value={
                            "id": 1,
                            "source_id": self.source_ids.get(Provider.PROVIDER_AWS),
                            "application_type_id": COST_MGMT_APP_TYPE_ID,
                            "authtype": choice(list(AUTH_TYPES.values())),
                        },
                    )
                    mock_consumer = MockKafkaConsumer([msg])
                    with patch(test.get("path"), side_effect=test.get("exception")):
                        with patch("sources.kafka_listener.time.sleep") as mock_time:
                            with patch("sources.kafka_listener.close_and_set_db_connection"):
                                source_integration.listen_for_messages(msg, mock_consumer, COST_MGMT_APP_TYPE_ID)
                                mock_time.assert_called()

    def test_execute_koku_provider_op_create(self):
        """Test to execute Koku Operations to sync with Sources for creation."""
        source_id = self.source_ids.get(Provider.PROVIDER_AWS)
        provider = Sources(**self.sources.get(Provider.PROVIDER_AWS))
        provider.save()

        msg = {"operation": "create", "provider": provider, "offset": provider.offset}
        with patch.object(SourcesHTTPClient, "set_source_status"):
            with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
                source_integration.execute_koku_provider_op(msg)
        self.assertIsNotNone(Sources.objects.get(source_id=source_id).koku_uuid)
        self.assertFalse(Sources.objects.get(source_id=source_id).pending_update)
        self.assertEqual(Sources.objects.get(source_id=source_id).koku_uuid, str(provider.source_uuid))

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_execute_koku_provider_op_destroy(self):
        """Test to execute Koku Operations to sync with Sources for destruction."""
        source_id = self.source_ids.get(Provider.PROVIDER_AWS)
        provider = Sources(**self.sources.get(Provider.PROVIDER_AWS))
        provider.save()

        msg = {"operation": "destroy", "provider": provider, "offset": provider.offset}
        with patch.object(SourcesHTTPClient, "set_source_status"):
            source_integration.execute_koku_provider_op(msg)
        self.assertEqual(Sources.objects.filter(source_id=source_id).exists(), False)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_execute_koku_provider_op_destroy_provider_not_found(self):
        """Test to execute Koku Operations to sync with Sources for destruction with provider missing.

        First, raise ProviderBuilderError. Check that provider and source still exists.
        Then, re-call provider destroy without exception, then see both source and provider are gone.

        """
        source_id = self.source_ids.get(Provider.PROVIDER_AWS)
        provider = Sources(**self.sources.get(Provider.PROVIDER_AWS))
        provider.save()
        # check that the source exists
        self.assertTrue(Sources.objects.filter(source_id=source_id).exists())

        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            builder = SourcesProviderCoordinator(source_id, provider.auth_header, provider.account_id, provider.org_id)
            builder.create_account(provider)

        self.assertTrue(Provider.objects.filter(uuid=provider.source_uuid).exists())
        provider = Sources.objects.get(source_id=source_id)

        msg = {"operation": "destroy", "provider": provider, "offset": provider.offset}

        with patch.object(SourcesHTTPClient, "set_source_status"):
            with patch.object(ProviderBuilder, "destroy_provider", side_effect=raise_provider_manager_error):
                source_integration.execute_koku_provider_op(msg)
                self.assertTrue(Provider.objects.filter(uuid=provider.source_uuid).exists())
                self.assertTrue(Sources.objects.filter(source_uuid=provider.source_uuid).exists())
                self.assertTrue(Sources.objects.filter(koku_uuid=provider.source_uuid).exists())

        with patch.object(SourcesHTTPClient, "set_source_status"):
            source_integration.execute_koku_provider_op(msg)
        self.assertFalse(Provider.objects.filter(uuid=provider.source_uuid).exists())

    def test_execute_koku_provider_op_update(self):
        """Test to execute Koku Operations to sync with Sources for update."""

        def set_status_helper(*args, **kwargs):
            """helper to clear update flag."""
            storage.clear_update_flag(source_id)

        source_id = self.source_ids.get(Provider.PROVIDER_AWS)
        provider = Sources(**self.sources.get(Provider.PROVIDER_AWS))
        provider.save()

        msg = {"operation": "create", "provider": provider, "offset": provider.offset}
        with patch.object(SourcesHTTPClient, "set_source_status"):
            with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
                source_integration.execute_koku_provider_op(msg)

        builder = SourcesProviderCoordinator(source_id, provider.auth_header, provider.account_id, provider.org_id)

        source = storage.get_source_instance(source_id)
        uuid = source.koku_uuid

        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            builder.update_account(source)

        self.assertEqual(
            Provider.objects.get(uuid=uuid).billing_source.data_source,
            self.sources.get(Provider.PROVIDER_AWS).get("billing_source").get("data_source"),
        )

        provider.billing_source = {"data_source": {"bucket": "new-bucket"}}
        provider.koku_uuid = uuid
        provider.pending_update = True
        provider.save()

        msg = {"operation": "update", "provider": provider, "offset": provider.offset}
        with patch.object(SourcesHTTPClient, "set_source_status", side_effect=set_status_helper):
            with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
                source_integration.execute_koku_provider_op(msg)
        response = Sources.objects.get(source_id=source_id)
        self.assertEqual(response.pending_update, False)
        self.assertEqual(response.billing_source, {"data_source": {"bucket": "new-bucket"}})

        response = Provider.objects.get(uuid=uuid)
        self.assertEqual(response.billing_source.data_source.get("bucket"), "new-bucket")

    def test_execute_koku_provider_op_skip_status(self):
        """Test to execute Koku Operations to sync with Sources and not push status."""
        source_id = self.source_ids.get(Provider.PROVIDER_AWS)
        provider = Sources(**self.sources.get(Provider.PROVIDER_AWS))
        provider.save()

        msg = {"operation": "create", "provider": provider, "offset": provider.offset}
        with patch.object(SourcesHTTPClient, "set_source_status"):
            with patch.object(ProviderAccessor, "cost_usage_source_ready", side_effect=SkipStatusPush):
                source_integration.execute_koku_provider_op(msg)
        self.assertEqual(Sources.objects.get(source_id=source_id).status, {})

    def test_collect_pending_items(self):
        """Test to load the in-progress queue."""
        aws_source = Sources(
            source_id=1,
            auth_header=Config.SOURCES_FAKE_HEADER,
            offset=1,
            name="AWS Source",
            source_type=Provider.PROVIDER_AWS,
            authentication="fakeauth",
            billing_source="s3bucket",
        )
        aws_source.save()

        aws_source_incomplete = Sources(
            source_id=2,
            auth_header=Config.SOURCES_FAKE_HEADER,
            offset=2,
            name="AWS Source 2",
            source_type=Provider.PROVIDER_AWS,
        )
        aws_source_incomplete.save()

        ocp_source = Sources(
            source_id=3,
            auth_header=Config.SOURCES_FAKE_HEADER,
            authentication="fakeauth",
            offset=3,
            name="OCP Source",
            source_type=Provider.PROVIDER_OCP,
        )
        ocp_source.save()

        ocp_source_complete = Sources(
            source_id=4,
            auth_header=Config.SOURCES_FAKE_HEADER,
            offset=4,
            name="Complete OCP Source",
            source_type=Provider.PROVIDER_OCP,
            koku_uuid=faker.uuid4(),
        )
        ocp_source_complete.save()
        source_delete = Sources.objects.get(source_id=4)
        source_delete.pending_delete = True
        source_delete.save()

        response = source_integration._collect_pending_items()
        self.assertEqual(len(response), 3)

    # @patch.object(Config, "SOURCES_API_URL", "http://www.sources.com")
    # def test_process_message_application_unsupported_source_type(self):
    #     """Test the process_message function with an unsupported source type."""
    #     test_application_id = 2

    #     test = {
    #         "event": source_integration.KAFKA_APPLICATION_CREATE,
    #         "value": {"id": 1, "source_id": 1, "application_type_id": test_application_id},
    #     }
    #     msg_data = MsgDataGenerator(event_type=test.get("event"), value=test.get("value")).get_data()
    #     with patch.object(
    #         SourcesHTTPClient, "get_source_details", return_value={"name": "my ansible", "source_type_id": 2}
    #     ):
    #         with patch.object(SourcesHTTPClient, "get_application_settings", return_value={}):
    #             with patch.object(SourcesHTTPClient, "get_source_type_name", return_value="ansible-tower"):
    #                 # self.assertIsNone(process_message(test_application_id, msg_data))
    #                 self.assertIsNone(msg_data)
    #                 pass

    @patch("sources.kafka_listener.execute_koku_provider_op")
    def test_process_synchronize_sources_msg_db_error(self, mock_process_message):
        """Test processing synchronize messages with database errors."""
        provider = Sources.objects.create(**self.sources.get(Provider.PROVIDER_AWS))
        provider.save()

        test_queue = queue.PriorityQueue()

        test_matrix = [
            {"test_value": {"operation": "update", "provider": provider}, "side_effect": InterfaceError},
            {"test_value": {"operation": "update", "provider": provider}, "side_effect": OperationalError},
        ]

        for i, test in enumerate(test_matrix):
            mock_process_message.side_effect = test.get("side_effect")
            with patch("sources.kafka_listener.close_and_set_db_connection") as close_mock:
                with patch.object(Config, "RETRY_SECONDS", 0):
                    process_synchronize_sources_msg((i, test["test_value"]), test_queue)
                    close_mock.assert_called()
        for i in range(2):
            priority, _ = test_queue.get_nowait()
            self.assertEqual(priority, i)

    @patch("sources.kafka_listener.execute_koku_provider_op")
    def test_process_synchronize_sources_msg_integration_error(self, mock_process_message):
        """Test processing synchronize messages with database errors."""
        provider = Sources.objects.create(**self.sources.get(Provider.PROVIDER_AWS))
        provider.save()

        test_queue = queue.PriorityQueue()

        test_matrix = [
            {"test_value": {"operation": "update", "provider": provider}, "side_effect": IntegrityError},
            {"test_value": {"operation": "update", "provider": provider}, "side_effect": SourcesIntegrationError},
        ]

        for i, test in enumerate(test_matrix):
            mock_process_message.side_effect = test.get("side_effect")
            with patch.object(Config, "RETRY_SECONDS", 0):
                process_synchronize_sources_msg((i, test["test_value"]), test_queue)
        for i in range(2):
            priority, _ = test_queue.get_nowait()
            self.assertEqual(priority, i)

    # @patch("sources.kafka_listener.execute_koku_provider_op")
    # def test_process_synchronize_sources_msg(self, mock_process_message):
    #     """Test processing synchronize messages."""
    #     provider = Sources(**self.aws_source)

    #     test_queue = queue.PriorityQueue()

    #     messages = [
    #         {"operation": "create", "provider": provider, "offset": provider.offset},
    #         {"operation": "update", "provider": provider},
    #     ]

    #     for msg in messages:
    #         with patch("sources.storage.clear_update_flag") as mock_clear_flag:
    #             process_synchronize_sources_msg((0, msg), test_queue)
    #             mock_clear_flag.assert_called()

    #     msg = {"operation": "destroy", "provider": provider}
    #     with patch("sources.storage.clear_update_flag") as mock_clear_flag:
    #         process_synchronize_sources_msg((0, msg), test_queue)
    #         mock_clear_flag.assert_not_called()

    def test_storage_callback_create(self):
        """Test storage callback puts create task onto queue."""
        local_source = Sources(**self.aws_local_source, pending_update=True)
        local_source.save()

        with patch("sources.kafka_listener.execute_process_queue"):
            storage_callback("", local_source)
            _, msg = PROCESS_QUEUE.get_nowait()
            self.assertEqual(msg.get("operation"), "create")

    def test_storage_callback_update(self):
        """Test storage callback puts update task onto queue."""
        uuid = self.aws_local_source.get("source_uuid")
        local_source = Sources(**self.aws_local_source, koku_uuid=uuid, pending_update=True)
        local_source.save()

        with (
            patch("sources.kafka_listener.execute_process_queue"),
            patch("sources.storage.screen_and_build_provider_sync_create_event", return_value=False),
        ):
            storage_callback("", local_source)
            _, msg = PROCESS_QUEUE.get_nowait()
            self.assertEqual(msg.get("operation"), "update")

    def test_storage_callback_update_and_delete(self):
        """Test storage callback only deletes on pending update and delete."""
        uuid = self.aws_local_source.get("source_uuid")
        local_source = Sources(**self.aws_local_source, koku_uuid=uuid, pending_update=True, pending_delete=True)
        local_source.save()

        with (
            patch("sources.kafka_listener.execute_process_queue"),
            patch("sources.storage.screen_and_build_provider_sync_create_event", return_value=False),
        ):
            storage_callback("", local_source)
            _, msg = PROCESS_QUEUE.get_nowait()
            self.assertEqual(msg.get("operation"), "destroy")
