#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import copy
import json
from itertools import product
from random import choice
from unittest.mock import MagicMock
from unittest.mock import patch
from uuid import uuid4

from django.db.models.signals import post_save
from django.test.utils import override_settings
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
from sources.kafka_message_processor import KAFKA_APPLICATION_PAUSE
from sources.kafka_message_processor import KAFKA_APPLICATION_UNPAUSE
from sources.kafka_message_processor import KAFKA_APPLICATION_UPDATE
from sources.kafka_message_processor import KAFKA_AUTHENTICATION_CREATE
from sources.kafka_message_processor import KAFKA_AUTHENTICATION_UPDATE
from sources.kafka_message_processor import KAFKA_SOURCE_DESTROY
from sources.kafka_message_processor import KAFKA_SOURCE_UPDATE
from sources.kafka_message_processor import KafkaMessageProcessor
from sources.kafka_message_processor import SourceDetails
from sources.kafka_message_processor import SourceMsgProcessor
from sources.kafka_message_processor import SOURCES_AWS_SOURCE_NAME
from sources.kafka_message_processor import SOURCES_AZURE_SOURCE_NAME
from sources.kafka_message_processor import SOURCES_GCP_SOURCE_NAME
from sources.kafka_message_processor import SOURCES_OCP_SOURCE_NAME
from sources.kafka_message_processor import SourcesMessageError
from sources.sources_http_client import AUTH_TYPES
from sources.sources_http_client import SourcesHTTPClient
from sources.sources_http_client import SourcesHTTPClientError
from sources.test.test_sources_http_client import COST_MGMT_APP_TYPE_ID

NoneType = type(None)

EVENT_LIST = [
    KAFKA_APPLICATION_CREATE,
    KAFKA_APPLICATION_DESTROY,
    KAFKA_APPLICATION_UPDATE,
    KAFKA_APPLICATION_PAUSE,
    KAFKA_APPLICATION_UNPAUSE,
    KAFKA_AUTHENTICATION_CREATE,
    KAFKA_AUTHENTICATION_UPDATE,
    KAFKA_SOURCE_DESTROY,
    KAFKA_SOURCE_UPDATE,
]
FAKER = Faker()
PROVIDER_LIST = [Provider.PROVIDER_AWS, Provider.PROVIDER_AZURE, Provider.PROVIDER_GCP, Provider.PROVIDER_OCP]
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


def msg_generator(event_type, topic=None, offset=None, value: dict = None, header=Config.SOURCES_FAKE_HEADER):
    test_value = '{"id":1,"source_id":1,"application_type_id":2}'
    if value:
        test_value = json.dumps(value)
    return ConsumerRecord(
        topic=topic or "platform.sources.event-stream",
        offset=offset or 5,
        event_type=event_type,
        auth_header=header,
        value=bytes(test_value, encoding="utf-8"),
    )


def mock_details_generator(provider_type, name, uid, source_id):
    """Generates a fake source details dict."""
    source_type_id = SOURCE_TYPE_IDS_MAP.get(provider_type, 0)
    details = {"name": name, "source_type_id": source_type_id, "uid": uid}
    with patch.object(SourcesHTTPClient, "get_source_details", return_value=details):
        with patch.object(
            SourcesHTTPClient, "get_source_type_name", return_value=SOURCE_TYPE_IDS.get(source_type_id, "unknown")
        ):
            return SourceDetails(Config.SOURCES_FAKE_HEADER, source_id, 10001, 1234567)


class ConsumerRecord:
    """Test class for kafka msg."""

    def __init__(self, topic, offset, event_type, value, auth_header=None, partition=0, account_id="10001"):
        """Initialize Msg."""
        self._topic = topic
        self._offset = offset
        self._partition = partition
        if auth_header:
            self._headers = (
                ("event_type", bytes(event_type, encoding="utf-8")),
                ("x-rh-identity", bytes(auth_header, encoding="utf-8")),
                ("x-rh-sources-account-number", bytes(account_id, encoding="utf-8")),
            )
        else:
            self._headers = (("event_type", bytes(event_type, encoding="utf-8")),)
        self._value = value

    def topic(self):
        return self._topic

    def offset(self):
        return self._offset

    def partition(self):
        return self._partition

    def value(self):
        return self._value

    def headers(self):
        return self._headers


class KafkaMessageProcessorTest(IamTestCase):
    """Test cases for KafkaMessageProcessor."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        post_save.disconnect(storage_callback, sender=Sources)
        account = "10001"
        org_id = "1234567"
        IdentityHeaderMiddleware.create_customer(account, org_id, "POST")

    def setUp(self):
        self.valid_creds = {
            Provider.PROVIDER_AWS: {"role_arn": "password"},
            Provider.PROVIDER_AZURE: {
                "client_id": "client-id",
                "client_secret": "password",
                "subscription_id": "subscription_id",
                "tenant_id": "tenant_id",
            },
            Provider.PROVIDER_GCP: {"project_id": "project_id"},
            Provider.PROVIDER_OCP: {"cluster_id": "clister-id"},
        }
        self.valid_billing = {
            Provider.PROVIDER_AWS: {"bucket": "bucket"},
            Provider.PROVIDER_AZURE: {"resource_group": "rg1", "storage_account": "sa1"},
            Provider.PROVIDER_GCP: {"dataset": "dataset"},
            Provider.PROVIDER_OCP: {},
        }

    def test_fake_details_generator(self):
        """Test to ensure the generator makes things correctly."""
        provider_types = [
            Provider.PROVIDER_AWS,
            Provider.PROVIDER_AZURE,
            Provider.PROVIDER_GCP,
            Provider.PROVIDER_OCP,
        ]
        for provider in provider_types:
            with self.subTest(test=provider):
                uid = uuid4()
                name = FAKER.name()
                source_id = FAKER.pyint()
                details = mock_details_generator(provider, name, uid, source_id)
                self.assertIsInstance(details, SourceDetails)
                self.assertEqual(details.name, name)
                self.assertEqual(details.source_type, provider)
                self.assertEqual(details.source_type_name, SOURCE_TYPE_IDS[SOURCE_TYPE_IDS_MAP[provider]])
                self.assertEqual(details.source_uuid, uid)

    def test_create_msg_processor(self):
        """Test create_msg_processor returns the correct processor based on msg event."""
        test_mtx = [
            {"event_type": KAFKA_APPLICATION_CREATE, "expected": ApplicationMsgProcessor},
            {"event_type": KAFKA_APPLICATION_UPDATE, "expected": ApplicationMsgProcessor},
            {"event_type": KAFKA_APPLICATION_DESTROY, "expected": ApplicationMsgProcessor},
            {"event_type": KAFKA_APPLICATION_PAUSE, "expected": ApplicationMsgProcessor},
            {"event_type": KAFKA_APPLICATION_UNPAUSE, "expected": ApplicationMsgProcessor},
            {"event_type": KAFKA_AUTHENTICATION_CREATE, "expected": AuthenticationMsgProcessor},
            {"event_type": KAFKA_AUTHENTICATION_UPDATE, "expected": AuthenticationMsgProcessor},
            {"event_type": KAFKA_SOURCE_UPDATE, "expected": SourceMsgProcessor},
            {"event_type": KAFKA_SOURCE_DESTROY, "expected": NoneType},
            {"event_type": "Source.create", "expected": NoneType},
            {"event_type": KAFKA_APPLICATION_CREATE, "test_topic": "unknown", "expected": NoneType},
        ]

        for test in test_mtx:
            with self.subTest(test=test):
                msg = msg_generator(event_type=test.get("event_type"), topic=test.get("test_topic"))
                self.assertIsInstance(create_msg_processor(msg, COST_MGMT_APP_TYPE_ID), test.get("expected"))

    def test_create_msg_processor_various_headers_success(self):
        """Test create_msg_processor various kafka headers."""
        event = KAFKA_APPLICATION_CREATE
        account_id = "10002"
        table = [
            {
                "header_list": (
                    ("event_type", bytes(event, encoding="utf-8")),
                    ("x-rh-identity", bytes(Config.SOURCES_FAKE_HEADER, encoding="utf-8")),
                    ("x-rh-sources-account-number", bytes(account_id, encoding="utf-8")),
                ),
                "expected": {"account_number": account_id, "auth_header": Config.SOURCES_FAKE_HEADER},
            },
            {
                "header_list": (
                    ("event_type", bytes(event, encoding="utf-8")),
                    ("x-rh-identity", bytes(Config.SOURCES_FAKE_HEADER, encoding="utf-8")),
                ),
                "expected": {"account_number": "10001", "auth_header": Config.SOURCES_FAKE_HEADER},
            },
        ]
        for test in table:
            with self.subTest(test=test):
                msg = msg_generator(event_type=event)
                msg._headers = test.get("header_list")
                result = create_msg_processor(msg, COST_MGMT_APP_TYPE_ID)
                for k, v in test.get("expected").items():
                    self.assertEqual(getattr(result, k), v)

    def test_create_msg_processor_various_headers_failures(self):
        """Test create_msg_processor various kafka headers."""
        header_missing_account_number = "eyJpZGVudGl0eSI6IHsidXNlciI6IHsiaXNfb3JnX2FkbWluIjogImZhbHNlIiwgInVzZXJuYW1lIjogInNvdXJjZXMiLCAiZW1haWwiOiAic291cmNlc0Bzb3VyY2VzLmlvIn0sICJpbnRlcm5hbCI6IHsib3JnX2lkIjogIjU0MzIxIn19fQ=="  # noqa: E501
        event = KAFKA_APPLICATION_CREATE
        account_id = "10002"
        table = [
            {
                "header_list": (
                    ("event_type", bytes(event, encoding="utf-8")),
                    ("x-rh-identity", bytes(header_missing_account_number, encoding="utf-8")),
                )
            },
            {
                "header_list": (
                    ("event_type", bytes(event, encoding="utf-8")),
                    ("x-rh-sources-account-number", bytes(account_id, encoding="utf-8")),
                )
            },
            {
                "header_list": (
                    ("event_type", bytes(event, encoding="utf-8")),
                    ("x-rh-identity", bytes(header_missing_account_number, encoding="utf-8")),
                    ("x-rh-sources-account-number", b""),
                )
            },
        ]
        for test in table:
            with self.subTest(test=test):
                msg = msg_generator(event_type=event)
                msg._headers = test.get("header_list")
                with self.assertRaises(SourcesMessageError):
                    create_msg_processor(msg, COST_MGMT_APP_TYPE_ID)

    def test_create_msg_processor_missing_auth_and_account_id(self):
        """Test that KafkaMessageProcessor raises SourcesMessageError on missing info."""
        event = KAFKA_APPLICATION_CREATE
        msg = msg_generator(event_type=event, header=None)
        with self.assertRaises(SourcesMessageError):
            create_msg_processor(msg, COST_MGMT_APP_TYPE_ID)

    def test_create_msg_processor_missing_header(self):
        """Test create_msg_processor on a message missing kafka headers."""
        msg = msg_generator(event_type=KAFKA_APPLICATION_CREATE)
        msg._headers = {}  # override the generator headers
        self.assertIsInstance(create_msg_processor(msg, COST_MGMT_APP_TYPE_ID), NoneType)

    def test_schema_suffix_init(self):
        event = KAFKA_APPLICATION_CREATE
        cost_mgmt_id = 1
        table = [
            {"suffix": "", "expected": "1234567"},
            {"suffix": "567", "expected": "1234567"},
            {"suffix": "_real_suffix", "expected": "1234567_real_suffix"},
        ]
        for test in table:
            with override_settings(SCHEMA_SUFFIX=test["suffix"]):
                msg = msg_generator(
                    event_type=event, value={"id": 1, "source_id": 1, "application_type_id": COST_MGMT_APP_TYPE_ID}
                )
                got = KafkaMessageProcessor(msg, event, cost_mgmt_id)
                self.assertEqual(got.org_id, test["expected"])

    def test_msg_for_cost_mgmt(self):
        """Test msg_for_cost_mgmt true or false."""
        test_app_value_is_cost = {"id": 1, "source_id": 1, "application_type_id": COST_MGMT_APP_TYPE_ID}
        test_app_value_is_not_cost = {"id": 1, "source_id": 1, "application_type_id": COST_MGMT_APP_TYPE_ID + 1}
        test_auth_value_valid = {"id": 1, "source_id": 1, "authtype": choice(list(AUTH_TYPES.values()))}
        test_auth_value_invalid = {"id": 1, "source_id": 1, "authtype": "access_key_secret_key"}
        table = [
            # Source events
            {"processor": KafkaMessageProcessor, "event-type": "Source.create", "expected": False},
            {"processor": KafkaMessageProcessor, "event-type": KAFKA_SOURCE_UPDATE, "expected": True},
            {"processor": KafkaMessageProcessor, "event-type": KAFKA_SOURCE_DESTROY, "expected": False},
            # Application events
            {"event-type": KAFKA_APPLICATION_CREATE, "expected": True, "value": test_app_value_is_cost},
            {"event-type": KAFKA_APPLICATION_CREATE, "expected": False, "value": test_app_value_is_not_cost},
            {"event-type": KAFKA_APPLICATION_UPDATE, "expected": True, "value": test_app_value_is_cost},
            {"event-type": KAFKA_APPLICATION_UPDATE, "expected": False, "value": test_app_value_is_not_cost},
            {"event-type": KAFKA_APPLICATION_DESTROY, "expected": True, "value": test_app_value_is_cost},
            {"event-type": KAFKA_APPLICATION_DESTROY, "expected": False, "value": test_app_value_is_not_cost},
            {"event-type": KAFKA_APPLICATION_PAUSE, "expected": True, "value": test_app_value_is_cost},
            {"event-type": KAFKA_APPLICATION_PAUSE, "expected": False, "value": test_app_value_is_not_cost},
            {"event-type": KAFKA_APPLICATION_UNPAUSE, "expected": True, "value": test_app_value_is_cost},
            {"event-type": KAFKA_APPLICATION_UNPAUSE, "expected": False, "value": test_app_value_is_not_cost},
            # Authentication events
            {
                "event-type": KAFKA_AUTHENTICATION_CREATE,
                "expected": True,
                "patch": True,
                "value": test_auth_value_valid,
            },
            {
                "event-type": KAFKA_AUTHENTICATION_CREATE,
                "expected": False,
                "patch": False,
                "value": test_auth_value_valid,
            },
            {"event-type": KAFKA_AUTHENTICATION_CREATE, "expected": False, "value": test_auth_value_invalid},
            {
                "event-type": KAFKA_AUTHENTICATION_UPDATE,
                "expected": True,
                "patch": True,
                "value": test_auth_value_valid,
            },
            {
                "event-type": KAFKA_AUTHENTICATION_UPDATE,
                "expected": False,
                "patch": False,
                "value": test_auth_value_valid,
            },
            {"event-type": KAFKA_AUTHENTICATION_UPDATE, "expected": False, "value": test_auth_value_invalid},
        ]
        for test in table:
            with self.subTest(test=test):
                with patch.object(
                    SourcesHTTPClient, "get_application_type_is_cost_management", return_value=test.get("patch")
                ):
                    msg = msg_generator(event_type=test.get("event-type"), value=test.get("value"))
                    if test.get("processor"):
                        processor = test.get("processor")(msg, test.get("event-type"), COST_MGMT_APP_TYPE_ID)
                    else:
                        processor = create_msg_processor(msg, COST_MGMT_APP_TYPE_ID)
                    self.assertEqual(processor.msg_for_cost_mgmt(), test.get("expected"))

    def test_save_sources_details(self):
        """Test save_source_details calls storage method."""
        table = [{"return": None, "expected": False}, {"return": True, "expected": True}]
        event = choice(EVENT_LIST)
        msg = msg_generator(event)
        processor = KafkaMessageProcessor(msg, event, COST_MGMT_APP_TYPE_ID)
        for test, provider in product(table, PROVIDER_LIST):
            mock_details = mock_details_generator(provider, FAKER.name(), uuid4(), FAKER.pyint())
            with self.subTest(test=f"(test={test}, provider={provider}, mock_details={mock_details.__dict__})"):
                with patch.object(KafkaMessageProcessor, "get_source_details", return_value=mock_details):
                    with patch(
                        "sources.storage.add_provider_sources_details", return_value=test.get("return")
                    ) as mock_details_save:
                        result = processor.save_sources_details()
                        self.assertEqual(result, test.get("expected"))
                        mock_details_save.assert_called_once()

    def test_save_sources_details_unknown_source_type(self):
        """Test save_source_details does not call storage method."""
        provider_list = [Provider.PROVIDER_IBM, "unknown"]
        event = choice(EVENT_LIST)
        msg = msg_generator(event)
        processor = KafkaMessageProcessor(msg, event, COST_MGMT_APP_TYPE_ID)
        for provider in provider_list:
            mock_details = mock_details_generator(provider, FAKER.name(), uuid4(), FAKER.pyint())
            with self.subTest(test=f"(provider={provider}, mock_details={mock_details.__dict__})"):
                with patch.object(KafkaMessageProcessor, "get_source_details", return_value=mock_details):
                    with patch("sources.storage.add_provider_sources_details") as mock_details_save:
                        result = processor.save_sources_details()
                        self.assertIsNone(result)
                        mock_details_save.assert_not_called()

    def test_save_credentials(self):
        """Test save credentials calls add_provider_sources_auth_info."""
        event = choice(EVENT_LIST)
        msg = msg_generator(event)
        processor = KafkaMessageProcessor(msg, event, COST_MGMT_APP_TYPE_ID)
        with patch.multiple(  # Add all new providers here
            SourcesHTTPClient,
            _get_aws_credentials=MagicMock(return_value=self.valid_creds.get(Provider.PROVIDER_AWS)),
            _get_azure_credentials=MagicMock(return_value=self.valid_creds.get(Provider.PROVIDER_AZURE)),
            _get_gcp_credentials=MagicMock(return_value=self.valid_creds.get(Provider.PROVIDER_GCP)),
            _get_ocp_credentials=MagicMock(return_value=self.valid_creds.get(Provider.PROVIDER_OCP)),
        ):
            table = [{"return": None, "expected": False}, {"return": True, "expected": True}]
            for test, provider in product(table, PROVIDER_LIST):
                with self.subTest(test=(test, provider)):
                    with patch("sources.storage.get_source_type", return_value=provider):
                        with patch(
                            "sources.storage.add_provider_sources_auth_info", return_value=test.get("return")
                        ) as mock_add:
                            result = processor.save_credentials()
                            self.assertEqual(result, test.get("expected"))
                            mock_add.assert_called_with(None, {"credentials": self.valid_creds.get(provider)})

    def test_save_credentials_errors(self):
        """Test save credentials when get_credentials raises exception."""
        event = choice(EVENT_LIST)
        msg = msg_generator(event)
        processor = KafkaMessageProcessor(msg, event, COST_MGMT_APP_TYPE_ID)
        with patch.multiple(
            SourcesHTTPClient,
            _get_aws_credentials=MagicMock(side_effect=SourcesHTTPClientError),
            _get_azure_credentials=MagicMock(side_effect=SourcesHTTPClientError),
            _get_gcp_credentials=MagicMock(side_effect=SourcesHTTPClientError),
            _get_ocp_credentials=MagicMock(side_effect=SourcesHTTPClientError),
        ):
            for provider in Provider.PROVIDER_LIST:
                with self.subTest(test=provider):
                    with patch("sources.storage.get_source_type", return_value=provider):
                        with patch.object(SourcesHTTPClient, "set_source_status") as mock_set:
                            with patch("sources.storage.add_provider_sources_auth_info") as mock_add:
                                with self.assertRaises(SourcesHTTPClientError):
                                    result = processor.save_credentials()
                                    self.assertIsNone(result)
                                    mock_set.assert_called_once()
                                    mock_add.assert_not_called()

    def test_save_billing_source(self):
        """Test save billing source calls add_provider_sources_billing_info."""

        def side_effect_func(arg, _):
            """Helper func to mock client.get_data_source call."""
            values = {  # add new sources here
                Provider.PROVIDER_AWS: self.valid_billing.get(Provider.PROVIDER_AWS),
                Provider.PROVIDER_AZURE: self.valid_billing.get(Provider.PROVIDER_AZURE),
                Provider.PROVIDER_GCP: self.valid_billing.get(Provider.PROVIDER_GCP),
                Provider.PROVIDER_OCP: self.valid_billing.get(Provider.PROVIDER_OCP),
            }
            return values.get(arg)

        event = choice(EVENT_LIST)
        msg = msg_generator(event)
        processor = KafkaMessageProcessor(msg, event, COST_MGMT_APP_TYPE_ID)
        with patch.object(SourcesHTTPClient, "get_data_source", side_effect=side_effect_func):
            new_list = copy.copy(PROVIDER_LIST)
            new_list.remove(Provider.PROVIDER_OCP)  # OCP is the oddball and does not save billing data
            table = [{"return": None, "expected": False}, {"return": True, "expected": True}]
            for test, provider in product(table, new_list):
                with self.subTest(test=(test, provider)):
                    with patch("sources.storage.get_source_type", return_value=provider):
                        with patch(
                            "sources.storage.add_provider_sources_billing_info", return_value=test.get("return")
                        ) as mock_add:
                            result = processor.save_billing_source()
                            self.assertEqual(result, test.get("expected"))
                            mock_add.assert_called_with(None, {"data_source": self.valid_billing.get(provider)})

    def test_save_billing_source_skipped_for_OCP(self):
        """Test that save_billing doesn't do anything for an OCP source."""
        event = choice(EVENT_LIST)
        msg = msg_generator(event)
        processor = KafkaMessageProcessor(msg, event, COST_MGMT_APP_TYPE_ID)
        provider = Provider.PROVIDER_OCP
        for saved in [True, None]:
            with self.subTest(test=saved):
                with patch("sources.storage.get_source_type", return_value=provider):
                    with patch("sources.storage.add_provider_sources_billing_info", return_value=saved) as mock_add:
                        result = processor.save_billing_source()
                        self.assertIsNone(result)
                        mock_add.assert_not_called()

    def test_save_billing_source_errors(self):
        """Test save billing source when get_data_source raises exception."""
        event = choice(EVENT_LIST)
        msg = msg_generator(event)
        processor = KafkaMessageProcessor(msg, event, COST_MGMT_APP_TYPE_ID)
        with patch.object(SourcesHTTPClient, "get_data_source", side_effect=SourcesHTTPClientError):
            new_list = copy.copy(Provider.PROVIDER_LIST)
            new_list.remove(Provider.PROVIDER_OCP)  # OCP is the oddball and does not save billing data
            for saved, provider in product([True, None], new_list):
                with self.subTest(test=(saved, provider)):
                    with patch("sources.storage.get_source_type", return_value=provider):
                        with patch.object(SourcesHTTPClient, "set_source_status") as mock_set:
                            with patch("sources.storage.add_provider_sources_billing_info") as mock_add:
                                with self.assertRaises(SourcesHTTPClientError):
                                    result = processor.save_billing_source()
                                    self.assertIsNone(result)
                                    mock_set.assert_called_once()
                                    mock_add.assert_not_called()
