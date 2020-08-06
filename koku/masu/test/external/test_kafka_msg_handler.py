#
# Copyright 2018 Red Hat, Inc.
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
"""Test the Kafka msg handler."""
import json
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime
from unittest.mock import patch

import requests_mock
from confluent_kafka import KafkaError
from django.db import InterfaceError
from django.db import OperationalError
from requests.exceptions import HTTPError

import masu.external.kafka_msg_handler as msg_handler
from api.provider.models import Provider
from masu.config import Config
from masu.external.accounts_accessor import AccountsAccessor
from masu.external.accounts_accessor import AccountsAccessorError
from masu.external.downloader.ocp.ocp_report_downloader import OCPReportDownloader
from masu.external.kafka_msg_handler import KafkaMsgHandlerError
from masu.processor.report_processor import ReportProcessorError
from masu.prometheus_stats import WORKER_REGISTRY
from masu.test import MasuTestCase


def raise_exception():
    """Raise a kafka error."""
    raise KafkaMsgHandlerError()


def raise_OSError(path):
    """Raise a OSError."""
    raise OSError()


class MockError(KafkaError):
    """Test error class."""


class MockMessage:
    """Test class for kafka msg."""

    def __init__(self, topic="mocked-topic", url="http://unreal", value_dict={}, offset=50, partition=0, error=None):
        """Initialize Msg."""
        if error:
            assert isinstance(error, MockError)
        self._error = error
        self._topic = topic
        self._offset = offset
        self._partition = partition
        value_dict.update({"url": url})
        value_str = json.dumps(value_dict)
        self._value = value_str.encode("utf-8")

    def error(self):
        return self._error

    def offset(self):
        return self._offset

    def partition(self):
        return self._partition

    def topic(self):
        return self._topic

    def value(self):
        return self._value


class MockKafkaConsumer:
    def __init__(self, preloaded_messages=None):
        if not preloaded_messages:
            preloaded_messages = MockMessage()
        self.preloaded_messages = preloaded_messages

    def store_offsets(self, msg):
        pass

    def poll(self, *args, **kwargs):
        return self.preloaded_messages.pop(0)

    def seek(self, *args, **kwargs):
        pass

    def commit(self):
        self.preloaded_messages.pop()


class KafkaMsgHandlerTest(MasuTestCase):
    """Test Cases for the Kafka msg handler."""

    def setUp(self):
        """Set up each test case."""
        super().setUp()
        logging.disable(logging.NOTSET)
        payload_file = open("./koku/masu/test/data/ocp/payload.tar.gz", "rb")
        bad_payload_file = open("./koku/masu/test/data/ocp/bad_payload.tar.gz", "rb")
        no_manifest_file = open("./koku/masu/test/data/ocp/no_manifest.tar.gz", "rb")

        self.tarball_file = payload_file.read()
        payload_file.close()

        self.bad_tarball_file = bad_payload_file.read()
        bad_payload_file.close()

        self.no_manifest_file = no_manifest_file.read()
        no_manifest_file.close()

        self.cluster_id = "my-ocp-cluster-1"
        self.date_range = "20190201-20190301"

    @patch("masu.external.kafka_msg_handler.listen_for_messages")
    @patch("masu.external.kafka_msg_handler.get_consumer")
    def test_listen_for_msg_loop(self, mock_consumer, mock_listen):
        """Test that the message loop only calls listen for messages on valid messages."""
        msg_list = [
            None,
            MockMessage(offset=1),
            MockMessage(offset=2, error=MockError(KafkaError._PARTITION_EOF)),
            MockMessage(offset=3, error=MockError(KafkaError._MSG_TIMED_OUT)),
        ]
        mock_consumer.return_value = MockKafkaConsumer(msg_list)
        with patch("itertools.count", side_effect=[[0, 1, 2, 3]]):  # mocking the infinite loop
            with self.assertLogs(logger="masu.external.kafka_msg_handler", level=logging.WARNING):
                msg_handler.listen_for_messages_loop()
        mock_listen.assert_called_once()

    @patch("masu.external.kafka_msg_handler.process_messages")
    def test_listen_for_messages(self, mock_process_message):
        """Test to listen for kafka messages."""
        mock_process_message.return_value = True

        test_matrix = [
            {
                "test_value": {
                    "account": "10001",
                    "category": "tar",
                    "metadata": {"reporter": "", "stale_timestamp": "0001-01-01T00:00:00Z"},
                },
                "expected_process": True,
            }
        ]
        for test in test_matrix:
            msg = MockMessage(
                topic="platform.upload.hccm",
                offset=5,
                url="https://insights-quarantine.s3.amazonaws.com/myfile",
                value_dict=test.get("test_value"),
            )

            mock_consumer = MockKafkaConsumer([msg])

            msg_handler.listen_for_messages(msg, mock_consumer)
            if test.get("expected_process"):
                mock_process_message.assert_called()
            else:
                mock_process_message.assert_not_called()

    @patch("masu.external.kafka_msg_handler.process_messages")
    def test_listen_for_messages_db_error(self, mock_process_message):
        """Test to listen for kafka messages with database errors."""
        mock_process_message.return_value = True

        test_matrix = [
            {
                "test_value": {
                    "account": "10001",
                    "category": "tar",
                    "metadata": {"reporter": "", "stale_timestamp": "0001-01-01T00:00:00Z"},
                },
                "side_effect": InterfaceError,
            },
            {
                "test_value": {
                    "account": "10001",
                    "category": "tar",
                    "metadata": {"reporter": "", "stale_timestamp": "0001-01-01T00:00:00Z"},
                },
                "side_effect": OperationalError,
            },
        ]
        for test in test_matrix:
            msg = MockMessage(
                topic="platform.upload.hccm",
                offset=5,
                url="https://insights-quarantine.s3.amazonaws.com/myfile",
                value_dict=test.get("test_value"),
            )

            mock_consumer = MockKafkaConsumer([msg])

            mock_process_message.side_effect = test.get("side_effect")
            with patch("masu.external.kafka_msg_handler.close_and_set_db_connection") as close_mock:
                with patch.object(Config, "RETRY_SECONDS", 0):
                    msg_handler.listen_for_messages(msg, mock_consumer)
                    close_mock.assert_called()

    @patch("masu.external.kafka_msg_handler.process_messages")
    def test_listen_for_messages_error(self, mock_process_message):
        """Test to listen for kafka messages with errors."""
        mock_process_message.return_value = False

        test_matrix = [
            {
                "test_value": {
                    "account": "10001",
                    "category": "tar",
                    "metadata": {"reporter": "", "stale_timestamp": "0001-01-01T00:00:00Z"},
                },
                "side_effect": KafkaMsgHandlerError,
            },
            {
                "test_value": {
                    "account": "10001",
                    "category": "tar",
                    "metadata": {"reporter": "", "stale_timestamp": "0001-01-01T00:00:00Z"},
                },
                "side_effect": ReportProcessorError,
            },
        ]
        for test in test_matrix:
            msg = MockMessage(
                topic="platform.upload.hccm",
                offset=5,
                url="https://insights-quarantine.s3.amazonaws.com/myfile",
                value_dict=test.get("test_value"),
            )

            mock_consumer = MockKafkaConsumer([msg])

            mock_process_message.side_effect = test.get("side_effect")
            with patch("masu.external.kafka_msg_handler.close_and_set_db_connection") as close_mock:
                with patch.object(Config, "RETRY_SECONDS", 0):
                    msg_handler.listen_for_messages(msg, mock_consumer)
                    close_mock.assert_not_called()

    def test_process_messages(self):
        """Test the process_message function."""

        def _expected_success_path(msg, test, confirmation_mock):
            confirmation_mock.assert_called()

        def _expected_fail_path(msg, test, confirmation_mock):
            confirmation_mock.assert_not_called()

        report_meta_1 = {
            "schema_name": "test_schema",
            "manifest_id": "1",
            "provider_uuid": uuid.uuid4(),
            "provider_type": "OCP",
            "compression": "UNCOMPRESSED",
            "file": "/path/to/file.csv",
            "date": datetime.today(),
        }
        summarize_manifest_uuid = uuid.uuid4()
        parquet_convert_uuid = uuid.uuid4()
        test_matrix = [
            {
                "test_value": {
                    "request_id": "1",
                    "account": "10001",
                    "category": "tar",
                    "metadata": {"reporter": "", "stale_timestamp": "0001-01-01T00:00:00Z"},
                },
                "handle_message_returns": (msg_handler.SUCCESS_CONFIRM_STATUS, [report_meta_1]),
                "summarize_manifest_returns": summarize_manifest_uuid,
                "parquet_convert_returns": parquet_convert_uuid,
                "expected_fn": _expected_success_path,
            },
            {
                "test_value": {
                    "request_id": "1",
                    "account": "10001",
                    "category": "tar",
                    "metadata": {"reporter": "", "stale_timestamp": "0001-01-01T00:00:00Z"},
                },
                "handle_message_returns": (msg_handler.FAILURE_CONFIRM_STATUS, None),
                "summarize_manifest_returns": summarize_manifest_uuid,
                "parquet_convert_returns": parquet_convert_uuid,
                "expected_fn": _expected_success_path,
            },
            {
                "test_value": {
                    "request_id": "1",
                    "account": "10001",
                    "category": "tar",
                    "metadata": {"reporter": "", "stale_timestamp": "0001-01-01T00:00:00Z"},
                },
                "handle_message_returns": (None, None),
                "summarize_manifest_returns": summarize_manifest_uuid,
                "parquet_convert_returns": parquet_convert_uuid,
                "expected_fn": _expected_fail_path,
            },
            {
                "test_value": {
                    "request_id": "1",
                    "account": "10001",
                    "category": "tar",
                    "metadata": {"reporter": "", "stale_timestamp": "0001-01-01T00:00:00Z"},
                },
                "handle_message_returns": (None, [report_meta_1]),
                "summarize_manifest_returns": summarize_manifest_uuid,
                "parquet_convert_returns": parquet_convert_uuid,
                "expected_fn": _expected_fail_path,
            },
        ]
        for test in test_matrix:
            with self.subTest(test=test):
                msg = MockMessage(
                    topic="platform.upload.hccm",
                    offset=5,
                    url="https://insights-quarantine.s3.amazonaws.com/myfile",
                    value_dict=test.get("test_value"),
                )
                with patch(
                    "masu.external.kafka_msg_handler.handle_message", return_value=test.get("handle_message_returns")
                ):
                    with patch(
                        "masu.external.kafka_msg_handler.summarize_manifest",
                        return_value=test.get("summarize_manifest_returns"),
                    ):
                        with patch(
                            "masu.external.kafka_msg_handler.convert_to_parquet",
                            return_value=test.get("parquet_convert_returns"),
                        ):
                            with patch("masu.external.kafka_msg_handler.process_report"):
                                with patch("masu.external.kafka_msg_handler.send_confirmation") as confirmation_mock:
                                    msg_handler.process_messages(msg)
                                    test.get("expected_fn")(msg, test, confirmation_mock)

    @patch("masu.external.kafka_msg_handler.close_and_set_db_connection")
    def test_handle_messages(self, _):
        """Test to ensure that kafka messages are handled."""
        hccm_msg = MockMessage(msg_handler.HCCM_TOPIC, "http://insights-upload.com/quarnantine/file_to_validate")
        advisor_msg = MockMessage("platform.upload.advisor", "http://insights-upload.com/quarnantine/file_to_validate")

        # Verify that when extract_payload is successful with 'hccm' message that SUCCESS_CONFIRM_STATUS is returned
        with patch("masu.external.kafka_msg_handler.extract_payload", return_value=None):
            self.assertEqual(msg_handler.handle_message(hccm_msg), (msg_handler.SUCCESS_CONFIRM_STATUS, None))

        # Verify that when extract_payload is not successful with 'hccm' message that FAILURE_CONFIRM_STATUS is returned
        with patch("masu.external.kafka_msg_handler.extract_payload", side_effect=msg_handler.KafkaMsgHandlerError):
            self.assertEqual(msg_handler.handle_message(hccm_msg), (msg_handler.FAILURE_CONFIRM_STATUS, None))

        # Verify that when None status is returned for non-hccm messages (we don't confirm these)
        self.assertEqual(msg_handler.handle_message(advisor_msg), (None, None))

        # Verify that when extract_payload has a OperationalError that KafkaMessageError is raised
        with patch("masu.external.kafka_msg_handler.extract_payload", side_effect=OperationalError):
            with patch("django.db.connection.close") as mock_close:
                with self.assertRaises(KafkaMsgHandlerError):
                    msg_handler.handle_message(hccm_msg)
                    mock_close.assert_called()

        # Verify that when extract_payload has a InterfaceError that KafkaMessageError is raised
        with patch("masu.external.kafka_msg_handler.extract_payload", side_effect=InterfaceError):
            with patch("django.db.connection.close") as mock_close:
                with self.assertRaises(KafkaMsgHandlerError):
                    msg_handler.handle_message(hccm_msg)
                    mock_close.assert_called()

    def test_process_report(self):
        """Test report processing."""
        report_meta = {
            "schema_name": "test_schema",
            "manifest_id": "1",
            "provider_uuid": uuid.uuid4(),
            "provider_type": "OCP",
            "compression": "UNCOMPRESSED",
            "file": "/path/to/file.csv",
        }
        with patch("masu.external.kafka_msg_handler._process_report_file") as mock_process:
            msg_handler.process_report("request_id", report_meta)
            mock_process.assert_called()

    def test_summarize_manifest(self):
        """Test report summarization."""
        report_meta = {
            "schema_name": "test_schema",
            "manifest_id": "1",
            "provider_uuid": uuid.uuid4(),
            "provider_type": "OCP",
            "compression": "UNCOMPRESSED",
            "file": "/path/to/file.csv",
        }

        class FakeManifest:
            def __init__(self, num_processed_files=1, num_total_files=1):
                self.num_processed_files = num_processed_files
                self.num_total_files = num_total_files

            def get_manifest_by_id(self, manifest_id):
                return self

            def manifest_ready_for_summary(self, manifest_id):
                return self.num_processed_files == self.num_total_files

        # Check when manifest is done
        mock_manifest_accessor = FakeManifest(num_processed_files=2, num_total_files=2)

        with patch("masu.external.kafka_msg_handler.ReportManifestDBAccessor") as mock_accessor:
            mock_accessor.return_value.__enter__.return_value = mock_manifest_accessor
            with patch("masu.external.kafka_msg_handler.summarize_reports.delay") as mock_summarize_reports:
                msg_handler.summarize_manifest(report_meta)
                mock_summarize_reports.assert_called()

        # Check when manifest is not done
        mock_manifest_accessor = FakeManifest(num_processed_files=1, num_total_files=2)

        with patch("masu.external.kafka_msg_handler.ReportManifestDBAccessor") as mock_accessor:
            mock_accessor.return_value.__enter__.return_value = mock_manifest_accessor
            with patch("masu.external.kafka_msg_handler.summarize_reports.delay") as mock_summarize_reports:
                msg_handler.summarize_manifest(report_meta)
                mock_summarize_reports.assert_not_called()

    def test_extract_payload(self):
        """Test to verify extracting payload is successful."""

        fake_account = {"provider_uuid": uuid.uuid4(), "provider_type": "OCP", "schema_name": "testschema"}
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"
        with requests_mock.mock() as m:
            m.get(payload_url, content=self.tarball_file)

            fake_dir = tempfile.mkdtemp()
            fake_pvc_dir = tempfile.mkdtemp()
            with patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir):
                with patch.object(Config, "TMP_DIR", fake_dir):
                    with patch(
                        "masu.external.kafka_msg_handler.get_account_from_cluster_id", return_value=fake_account
                    ):
                        with patch("masu.external.kafka_msg_handler.create_manifest_entries", return_value=1):
                            with patch("masu.external.kafka_msg_handler.record_report_status", returns=None):
                                msg_handler.extract_payload(payload_url, "test_request_id")
                                expected_path = "{}/{}/{}/".format(
                                    Config.INSIGHTS_LOCAL_REPORT_DIR, self.cluster_id, self.date_range
                                )
                                self.assertTrue(os.path.isdir(expected_path))
                                shutil.rmtree(fake_dir)
                                shutil.rmtree(fake_pvc_dir)

    def test_extract_payload_no_account(self):
        """Test to verify extracting payload when no provider exists."""
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"
        with requests_mock.mock() as m:
            m.get(payload_url, content=self.tarball_file)

            fake_dir = tempfile.mkdtemp()
            fake_pvc_dir = tempfile.mkdtemp()
            with patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir):
                with patch.object(Config, "TMP_DIR", fake_dir):
                    with patch("masu.external.kafka_msg_handler.get_account_from_cluster_id", return_value=None):
                        self.assertFalse(msg_handler.extract_payload(payload_url, "test_request_id"))
                        shutil.rmtree(fake_dir)
                        shutil.rmtree(fake_pvc_dir)

    def test_extract_incomplete_file_payload(self):
        """Test to verify extracting payload missing report files is successful."""
        fake_account = {"provider_uuid": uuid.uuid4(), "provider_type": "OCP", "schema_name": "testschema"}
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"
        with requests_mock.mock() as m:
            m.get(payload_url, content=self.bad_tarball_file)

            fake_dir = tempfile.mkdtemp()
            fake_pvc_dir = tempfile.mkdtemp()
            with patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir):
                with patch.object(Config, "TMP_DIR", fake_dir):
                    with patch(
                        "masu.external.kafka_msg_handler.get_account_from_cluster_id", return_value=fake_account
                    ):
                        with patch("masu.external.kafka_msg_handler.create_manifest_entries", return_value=1):
                            with patch("masu.external.kafka_msg_handler.record_report_status"):
                                msg_handler.extract_payload(payload_url, "test_request_id")
                                expected_path = "{}/{}/{}/".format(
                                    Config.INSIGHTS_LOCAL_REPORT_DIR, self.cluster_id, self.date_range
                                )
                                self.assertFalse(os.path.isdir(expected_path))
                                shutil.rmtree(fake_dir)
                                shutil.rmtree(fake_pvc_dir)

    def test_extract_no_manifest(self):
        """Test to verify extracting payload missing a manifest is not successful."""
        fake_account = {"provider_uuid": uuid.uuid4(), "provider_type": "OCP", "schema_name": "testschema"}
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"
        with requests_mock.mock() as m:
            m.get(payload_url, content=self.no_manifest_file)

            fake_dir = tempfile.mkdtemp()
            fake_pvc_dir = tempfile.mkdtemp()
            with patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir):
                with patch.object(Config, "TMP_DIR", fake_dir):
                    with patch(
                        "masu.external.kafka_msg_handler.get_account_from_cluster_id", return_value=fake_account
                    ):
                        with patch("masu.external.kafka_msg_handler.create_manifest_entries", returns=1):
                            with patch("masu.external.kafka_msg_handler.record_report_status"):
                                with self.assertRaises(msg_handler.KafkaMsgHandlerError):
                                    msg_handler.extract_payload(payload_url, "test_request_id")
                                shutil.rmtree(fake_dir)
                                shutil.rmtree(fake_pvc_dir)

    @patch("masu.external.kafka_msg_handler.TarFile.extractall", side_effect=raise_OSError)
    def test_extract_bad_payload_not_tar(self, mock_extractall):
        """Test to verify extracting payload missing report files is not successful."""
        fake_account = {"provider_uuid": uuid.uuid4(), "provider_type": "OCP", "schema_name": "testschema"}
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"
        with requests_mock.mock() as m:
            m.get(payload_url, content=self.bad_tarball_file)

            fake_dir = tempfile.mkdtemp()
            fake_pvc_dir = tempfile.mkdtemp()
            with patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir):
                with patch.object(Config, "TMP_DIR", fake_dir):
                    with patch(
                        "masu.external.kafka_msg_handler.get_account_from_cluster_id", return_value=fake_account
                    ):
                        with patch("masu.external.kafka_msg_handler.create_manifest_entries", returns=1):
                            with patch("masu.external.kafka_msg_handler.record_report_status"):
                                with self.assertRaises(msg_handler.KafkaMsgHandlerError):
                                    msg_handler.extract_payload(payload_url, "test_request_id")
                                shutil.rmtree(fake_dir)
                                shutil.rmtree(fake_pvc_dir)

    def test_extract_payload_bad_url(self):
        """Test to verify extracting payload exceptions are handled."""
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"

        with requests_mock.mock() as m:
            m.get(payload_url, exc=HTTPError)

            with self.assertRaises(msg_handler.KafkaMsgHandlerError):
                msg_handler.extract_payload(payload_url, "test_request_id")

    def test_extract_payload_unable_to_open(self):
        """Test to verify extracting payload exceptions are handled."""
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"

        with requests_mock.mock() as m:
            m.get(payload_url, content=self.tarball_file)
            with patch("masu.external.kafka_msg_handler.open") as mock_oserror:
                mock_oserror.side_effect = PermissionError
                with self.assertRaises(msg_handler.KafkaMsgHandlerError):
                    msg_handler.extract_payload(payload_url, "test_request_id")

    def test_extract_payload_wrong_file_type(self):
        """Test to verify extracting payload is successful."""
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"

        with requests_mock.mock() as m:
            payload_file = open("./koku/masu/test/data/test_cur.csv", "rb")
            csv_file = payload_file.read()
            payload_file.close()

            m.get(payload_url, content=csv_file)

            with self.assertRaises(msg_handler.KafkaMsgHandlerError):
                msg_handler.extract_payload(payload_url, "test_request_id")

    def test_get_account_from_cluster_id(self):
        """Test to find account from cluster id."""
        cluster_id = uuid.uuid4()
        fake_account = {"provider_uuid": uuid.uuid4(), "provider_type": "OCP", "schema_name": "testschema"}

        def _expected_account_response(account, test):
            self.assertEqual(test.get("get_account_response"), account)

        def _expected_none_response(account, test):
            self.assertEqual(None, account)

        test_matrix = [
            {
                "get_provider_uuid_response": uuid.uuid4(),
                "get_account_response": fake_account,
                "expected_fn": _expected_account_response,
            },
            {
                "get_provider_uuid_response": None,
                "get_account_response": fake_account,
                "expected_fn": _expected_none_response,
            },
        ]

        context = {"cluster_id": cluster_id}
        for test in test_matrix:
            with patch(
                "masu.external.kafka_msg_handler.utils.get_provider_uuid_from_cluster_id",
                return_value=test.get("get_provider_uuid_response"),
            ):
                with patch(
                    "masu.external.kafka_msg_handler.get_account", return_value=test.get("get_account_response")
                ):
                    account = msg_handler.get_account_from_cluster_id(cluster_id, "test_request_id", context)
                    test.get("expected_fn")(account, test)

    def test_create_manifest_entries(self):
        """Test to create manifest entries."""
        report_meta = {
            "schema_name": "test_schema",
            "manifest_id": "1",
            "provider_uuid": uuid.uuid4(),
            "provider_type": "OCP",
            "compression": "UNCOMPRESSED",
            "file": "/path/to/file.csv",
            "date": datetime.today(),
            "uuid": uuid.uuid4(),
        }
        with patch.object(OCPReportDownloader, "_prepare_db_manifest_record", return_value=1):
            self.assertEqual(1, msg_handler.create_manifest_entries(report_meta, "test_request_id"))

    def test_send_confirmation_error(self):
        """Set up the test for raising a kafka error during sending confirmation."""
        # grab the connection error count before
        connection_errors_before = WORKER_REGISTRY.get_sample_value("kafka_connection_errors_total")
        with patch("masu.external.kafka_msg_handler.get_producer", side_effect=KafkaMsgHandlerError):
            with self.assertRaises(msg_handler.KafkaMsgHandlerError):
                msg_handler.send_confirmation(request_id="foo", status=msg_handler.SUCCESS_CONFIRM_STATUS)
            # assert that the error caused the kafka error metric to be incremented
            connection_errors_after = WORKER_REGISTRY.get_sample_value("kafka_connection_errors_total")
            self.assertEqual(connection_errors_after - connection_errors_before, 1)

    def test_get_account(self):
        """Test that the account details are returned given a provider uuid."""
        ocp_account = msg_handler.get_account(self.ocp_test_provider_uuid, "test_request_id")
        self.assertIsNotNone(ocp_account)
        self.assertEqual(ocp_account.get("provider_type"), Provider.PROVIDER_OCP)

    @patch.object(AccountsAccessor, "get_accounts")
    def test_get_account_exception(self, mock_accessor):
        """Test that no account is returned upon exception."""
        mock_accessor.side_effect = AccountsAccessorError("Sample timeout error")
        ocp_account = msg_handler.get_account(self.ocp_test_provider_uuid, "test_request_id")
        self.assertIsNone(ocp_account)

    def test_delivery_callback(self):
        """Test that delivery callback raises KafkaMsgHandlerError."""
        msg = "a mock message"
        err = MockError(KafkaError._MSG_TIMED_OUT)
        with self.assertLogs(logger="masu.external.kafka_msg_handler", level=logging.INFO):
            msg_handler.delivery_callback(None, msg)

        with self.assertLogs(logger="masu.external.kafka_msg_handler", level=logging.ERROR):
            msg_handler.delivery_callback(err, msg)

    @patch("masu.external.kafka_msg_handler.create_daily_archives", return_value=[])
    def test_construct_parquet_reports(self, mock_daily_archives):
        """Test construct parquet reports."""
        report_meta = {"account": "testaccount", "provider_uuid": "abc", "manifest_id": 1, "date": "today"}

        reports = msg_handler.construct_parquet_reports(1, "context", report_meta, "/payload/path", "report_file")
        self.assertEqual(reports, [])
