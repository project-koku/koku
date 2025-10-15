#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Kafka msg handler."""
import copy
import gzip
import io
import json
import logging
import os
import shutil
import tarfile
import tempfile
import uuid
from datetime import date
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import requests_mock
from confluent_kafka import KafkaError
from django.db import InterfaceError
from django.db import OperationalError
from model_bakery import baker
from requests.exceptions import HTTPError

import masu.external.kafka_msg_handler as msg_handler
from common.queues import OCPQueue
from kafka_utils.utils import UPLOAD_TOPIC
from masu.config import Config
from masu.external.kafka_msg_handler import EmptyPayloadFileError
from masu.external.kafka_msg_handler import KafkaMsgHandlerError
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessorError
from masu.processor.report_processor import ReportProcessorError
from masu.prometheus_stats import WORKER_REGISTRY
from masu.test import MasuTestCase
from masu.util.ocp import common as utils
from reporting_common.models import CostUsageReportManifest

FILE_PATH_ONE = Path("path/to/file_one")
FILE_PATH_TWO = Path("path/to/file_two")


def raise_exception():
    """Raise a kafka error."""
    raise KafkaMsgHandlerError()


def raise_OSError(path):
    """Raise a OSError."""
    raise OSError()


class FakeManifest:
    def __init__(self, num_processed_files=1, num_total_files=1):
        self.num_processed_files = num_processed_files
        self.num_total_files = num_total_files

    def get_manifest_by_id(self, manifest_id):
        return self

    def manifest_ready_for_summary(self, manifest_id):
        return self.num_processed_files == self.num_total_files


class MockError(KafkaError):
    """Test error class."""


class MockMessage:
    """Test class for kafka msg."""

    def __init__(
        self,
        topic=UPLOAD_TOPIC,
        url="http://unreal",
        value_dict={},
        offset=50,
        partition=0,
        error=None,
        service=None,
    ):
        """Initialize Msg."""
        if error:
            assert isinstance(error, MockError)
        self._error = error
        self._topic = topic
        self._offset = offset
        self._partition = partition
        value_dict.update({"url": url, "b64_identity": "fake_identity"})
        value_str = json.dumps(value_dict)
        self._value = value_str.encode("utf-8")
        if service:
            self._headers = (("service", bytes(service, encoding="utf-8")),)
        else:
            self._headers = (("service", bytes("hccm", encoding="utf-8")),)

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

    def headers(self):
        return self._headers


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

    def subscribe(self, *args, **kwargs):
        pass


def fake_payload(payload_dir):
    tar_bytes_io = io.BytesIO()
    with tarfile.open(fileobj=tar_bytes_io, mode="w") as tar:
        for file_path in payload_dir.iterdir():
            if file_path.is_file():
                tar.add(file_path, arcname=file_path.name)
    tar_bytes_io.seek(0)
    gz_bytes_io = io.BytesIO()
    with gzip.GzipFile(fileobj=gz_bytes_io, mode="wb") as gz:
        gz.write(tar_bytes_io.read())
    return gz_bytes_io.getvalue()


class KafkaMsgHandlerTest(MasuTestCase):
    """Test Cases for the Kafka msg handler."""

    def setUp(self):
        """Set up each test case."""
        super().setUp()
        logging.disable(logging.NOTSET)

        self.test_payload_file = Path("./koku/masu/test/data/ocp/payload2.tar.gz")

        empty_file_payload_dir = Path("./koku/masu/test/data/ocp/empty-file-payload")
        self.empty_file_payload = fake_payload(empty_file_payload_dir)

        with open("./koku/masu/test/data/ocp/payload.tar.gz", "rb") as payload_file:
            self.tarball_file = payload_file.read()
        with open(self.test_payload_file, "rb") as payload_file_dates:
            self.dates_tarball = payload_file_dates.read()
        with open("./koku/masu/test/data/ocp/bad_payload.tar.gz", "rb") as bad_payload_file:
            self.bad_tarball_file = bad_payload_file.read()
        with open("./koku/masu/test/data/ocp/no_manifest.tar.gz", "rb") as no_manifest_file:
            self.no_manifest_file = no_manifest_file.read()
        with open("./koku/masu/test/data/ocp/ros_payload.tar.gz", "rb") as ros_payload_file:
            self.ros_tarball_file = ros_payload_file.read()
        with open("./koku/masu/test/data/ocp/outside_retention_payload.tar.gz", "rb") as retention_payload_file:
            self.retention_tarball_file = retention_payload_file.read()

        self.cluster_id = "my-ocp-cluster-1"
        self.date_range = "21190201-21190301"
        self.manifest_id = "1234"

        self.ocp_manifest = CostUsageReportManifest.objects.filter(cluster_id__isnull=True).first()
        self.ocp_manifest_id = self.ocp_manifest.id
        self.ocp_source = baker.make("Sources", provider=self.ocp_provider)

        manifest = utils.parse_manifest("koku/masu/test/data/ocp/payload2")
        manifest.manifest_id = self.ocp_manifest_id

        self.fake_payload_info = utils.PayloadInfo(
            request_id="random request id",
            manifest=manifest,
            source_id=1,
            provider_uuid=self.ocp_provider_uuid,
            provider_type="OCP",
            cluster_alias=self.cluster_id,
            account_id="10001",
            org_id="10001",
            schema_name=self.schema_name,
            trino_schema=self.schema_name,
        )

    @patch("masu.external.kafka_msg_handler.listen_for_messages")
    @patch("masu.external.kafka_msg_handler.get_consumer")
    def test_listen_for_msg_loop(self, mock_consumer, mock_listen):
        """Test that the message loop only calls listen for messages on valid messages."""
        msg_list = [
            None,
            MockMessage(offset=2, error=MockError(KafkaError._PARTITION_EOF)),
            MockMessage(offset=3, error=MockError(KafkaError._MSG_TIMED_OUT)),
            MockMessage(offset=1),  # this is the only message that will cause the `mock_listen` to assert called once
        ]
        mock_consumer.return_value = MockKafkaConsumer(msg_list)
        with patch("itertools.count", side_effect=[range(len(msg_list))]):  # mocking the infinite loop
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
                "service": "hccm",
                "expected_process": True,
            },
            {
                "test_value": {},
                "service": "not-hccm",
                "expected_process": False,
            },
        ]
        for test in test_matrix:
            msg = MockMessage(
                topic="platform.upload.announce",
                offset=5,
                url="https://insights-quarantine.s3.amazonaws.com/myfile",
                value_dict=test.get("test_value"),
                service=test.get("service"),
            )

            mock_consumer = MockKafkaConsumer([msg])

            msg_handler.listen_for_messages(msg, mock_consumer)
            if test.get("expected_process"):
                mock_process_message.assert_called()
            else:
                mock_process_message.assert_not_called()
            mock_process_message.reset_mock()

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
                topic="platform.upload.announce",
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
            {
                "test_value": {
                    "account": "10001",
                    "category": "tar",
                    "metadata": {"reporter": "", "stale_timestamp": "0001-01-01T00:00:00Z"},
                },
                "side_effect": ParquetReportProcessorError,
            },
        ]
        for test in test_matrix:
            msg = MockMessage(
                topic="platform.upload.announce",
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

        def _expect_report_mock_called(msg, test, process_report_mock):
            process_report_mock.assert_called()

        def _expect_report_mock_not_called(msg, test, process_report_mock):
            process_report_mock.assert_not_called()

        report_meta_1 = {
            "schema_name": "test_schema",
            "manifest_id": "1",
            "provider_uuid": uuid.uuid4(),
            "provider_type": "OCP",
            "compression": "UNCOMPRESSED",
            "files": ["/path/to/file.csv"],
            "date": datetime.today(),
        }
        report_meta_2 = copy.copy(report_meta_1) | {"daily_reports": True}
        report_meta_3 = copy.copy(report_meta_1) | {"daily_reports": True, "manifest_id": "10000"}
        summarize_manifest_uuid = uuid.uuid4()
        test_matrix = [
            {
                "test_value": {
                    "request_id": "1",
                    "account": "10001",
                    "category": "tar",
                    "metadata": {"reporter": "", "stale_timestamp": "0001-01-01T00:00:00Z"},
                },
                "handle_message_returns": (
                    msg_handler.SUCCESS_CONFIRM_STATUS,
                    [copy.copy(report_meta_1)],
                    self.manifest_id,
                ),
                "summarize_manifest_returns": summarize_manifest_uuid,
                "expected_fn": _expected_success_path,
                "processing_fn": _expect_report_mock_called,
            },
            {
                "test_value": {
                    "request_id": "1",
                    "account": "10001",
                    "category": "tar",
                    "metadata": {"reporter": "", "stale_timestamp": "0001-01-01T00:00:00Z"},
                },
                "handle_message_returns": (
                    msg_handler.SUCCESS_CONFIRM_STATUS,
                    [copy.copy(report_meta_2)],
                    self.manifest_id,
                ),
                "summarize_manifest_returns": summarize_manifest_uuid,
                "expected_fn": _expected_success_path,
                "processing_fn": _expect_report_mock_called,
            },
            {
                "test_value": {
                    "request_id": "1",
                    "account": "10001",
                    "category": "tar",
                    "metadata": {"reporter": "", "stale_timestamp": "0001-01-01T00:00:00Z"},
                },
                "handle_message_returns": (
                    msg_handler.SUCCESS_CONFIRM_STATUS,
                    [copy.copy(report_meta_3)],
                    self.manifest_id,
                ),
                "summarize_manifest_returns": summarize_manifest_uuid,
                "expected_fn": _expected_success_path,
                "processing_fn": _expect_report_mock_not_called,
            },
            {
                "test_value": {
                    "request_id": "1",
                    "account": "10001",
                    "category": "tar",
                    "metadata": {"reporter": "", "stale_timestamp": "0001-01-01T00:00:00Z"},
                },
                "handle_message_returns": (msg_handler.FAILURE_CONFIRM_STATUS, None, None),
                "summarize_manifest_returns": summarize_manifest_uuid,
                "expected_fn": _expected_success_path,
                "processing_fn": _expect_report_mock_not_called,
            },
            {
                "test_value": {
                    "request_id": "1",
                    "account": "10001",
                    "category": "tar",
                    "metadata": {"reporter": "", "stale_timestamp": "0001-01-01T00:00:00Z"},
                },
                "handle_message_returns": (None, None, None),
                "summarize_manifest_returns": summarize_manifest_uuid,
                "expected_fn": _expected_fail_path,
                "processing_fn": _expect_report_mock_not_called,
            },
            {
                "test_value": {
                    "request_id": "1",
                    "account": "10001",
                    "category": "tar",
                    "metadata": {"reporter": "", "stale_timestamp": "0001-01-01T00:00:00Z"},
                },
                "handle_message_returns": (None, [copy.copy(report_meta_1)], None),
                "summarize_manifest_returns": summarize_manifest_uuid,
                "expected_fn": _expected_fail_path,
                "processing_fn": _expect_report_mock_called,
            },
        ]
        for test in test_matrix:
            with self.subTest(test=test):
                msg = MockMessage(
                    topic="platform.upload.announce",
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
                        with patch("masu.external.kafka_msg_handler.process_report") as process_report_mock:
                            with patch("masu.external.kafka_msg_handler.send_confirmation") as confirmation_mock:
                                msg_handler.process_messages(msg)
                                test.get("expected_fn")(msg, test, confirmation_mock)
                                test.get("processing_fn")(msg, test, process_report_mock)

    def test_process_messages_empty_file_handling(self):
        """Test process_message handles empty files correctly when selecting report_meta for summarization."""
        base_report_meta = {
            "schema_name": "test_schema",
            "manifest_id": "1",
            "provider_uuid": uuid.uuid4(),
            "provider_type": "OCP",
            "compression": "UNCOMPRESSED",
            "files": ["/path/to/file.csv"],
            "date": datetime.today(),
            "current_file": "test_file.csv",
        }

        test_matrix = [
            {
                "name": "last_report_meta_is_empty_file",
                "description": "Last report_meta is empty, should use earlier valid one for summarization",
                "report_metas": [
                    base_report_meta.copy(),  # Valid file
                    {**base_report_meta.copy(), "process_complete": True},  # Empty file
                ],
                "expected_summarize_meta_index": 0,  # Should use first (valid) report_meta
                "expected_process_calls": 1,  # Only the first file should be processed
            },
            {
                "name": "multiple_empty_files_at_end",
                "description": "Multiple empty files at end, should use valid one from middle",
                "report_metas": [
                    base_report_meta.copy(),  # Valid file
                    {**base_report_meta.copy(), "current_file": "valid2.csv"},  # Valid file
                    {**base_report_meta.copy(), "process_complete": True, "current_file": "empty1.csv"},  # Empty
                    {**base_report_meta.copy(), "process_complete": True, "current_file": "empty2.csv"},  # Empty
                ],
                "expected_summarize_meta_index": 0,  # Should use first valid report_meta
                "expected_process_calls": 2,  # Both valid files should be processed
            },
            {
                "name": "all_files_are_empty",
                "description": "All files are empty, should fallback to last report_meta",
                "report_metas": [
                    {**base_report_meta.copy(), "process_complete": True, "current_file": "empty1.csv"},
                    {**base_report_meta.copy(), "process_complete": True, "current_file": "empty2.csv"},
                ],
                "expected_summarize_meta_index": 1,  # Should fallback to last report_meta
                "expected_process_calls": 0,  # No files should be processed (all are empty)
            },
            {
                "name": "no_empty_files",
                "description": "No empty files, existing behavior should work",
                "report_metas": [
                    base_report_meta.copy(),
                    {**base_report_meta.copy(), "current_file": "valid2.csv"},
                ],
                "expected_summarize_meta_index": 0,  # Should use first valid report_meta
                "expected_process_calls": 2,  # Both files should be processed (no empty files)
            },
            {
                "name": "empty_file_in_middle",
                "description": "Empty file in middle, should use first valid one",
                "report_metas": [
                    base_report_meta.copy(),  # Valid
                    {**base_report_meta.copy(), "process_complete": True, "current_file": "empty.csv"},  # Empty
                    {**base_report_meta.copy(), "current_file": "valid2.csv"},  # Valid
                ],
                "expected_summarize_meta_index": 0,  # Should use first valid report_meta
                "expected_process_calls": 2,  # Both valid files should be processed (empty file skipped)
            },
        ]

        for test in test_matrix:
            with self.subTest(test=test["name"]):
                msg = MockMessage(
                    topic="platform.upload.announce",
                    offset=5,
                    url="https://insights-upload.com/myfile",
                    value_dict={
                        "request_id": "1",
                        "account": "10001",
                        "category": "tar",
                        "metadata": {"reporter": "", "stale_timestamp": "0001-01-01T00:00:00Z"},
                    },
                )

                # Expected report_meta that should be passed to summarize_manifest
                expected_report_meta = test["report_metas"][test["expected_summarize_meta_index"]]

                with (
                    patch(
                        "masu.external.kafka_msg_handler.handle_message",
                        return_value=(msg_handler.SUCCESS_CONFIRM_STATUS, test["report_metas"], self.manifest_id),
                    ),
                    patch("masu.external.kafka_msg_handler.process_report", return_value=True) as mock_process,
                    patch("masu.external.kafka_msg_handler.report_metas_complete", return_value=True),
                    patch(
                        "masu.external.kafka_msg_handler.summarize_manifest", return_value=uuid.uuid4()
                    ) as mock_summarize,
                    patch("masu.external.kafka_msg_handler.send_confirmation"),
                ):
                    msg_handler.process_messages(msg)

                    # Verify summarize_manifest was called with the expected report_meta
                    mock_summarize.assert_called_once()
                    actual_report_meta = mock_summarize.call_args[0][0]

                    # Compare the report_meta that was passed to summarize_manifest
                    self.assertEqual(
                        actual_report_meta.get("current_file"),
                        expected_report_meta.get("current_file"),
                        f"Test '{test['name']}': Expected summarize_manifest to be called with "
                        f"report_meta for file '{expected_report_meta.get('current_file')}' "
                        f"but got '{actual_report_meta.get('current_file')}'",
                    )

                    # Verify process_report was called for non-empty files only
                    expected_process_calls = test["expected_process_calls"]
                    self.assertEqual(
                        mock_process.call_count,
                        expected_process_calls,
                        f"Test '{test['name']}': Expected process_report to be called "
                        f"{expected_process_calls} times but was called "
                        f"{mock_process.call_count} times",
                    )

    @patch("masu.external.kafka_msg_handler.close_and_set_db_connection")
    def test_handle_messages(self, _):
        """Test to ensure that kafka messages are handled."""
        hccm_msg = MockMessage(UPLOAD_TOPIC, "http://insights-upload.com/quarnantine/file_to_validate")

        # Verify that when extract_payload is successful with 'hccm' message that SUCCESS_CONFIRM_STATUS is returned
        with patch("masu.external.kafka_msg_handler.extract_payload", return_value=(None, None)):
            self.assertEqual(msg_handler.handle_message(hccm_msg), (msg_handler.SUCCESS_CONFIRM_STATUS, None, None))

        # Verify that when extract_payload is not successful with 'hccm' message
        # that FAILURE_CONFIRM_STATUS is returned
        with patch("masu.external.kafka_msg_handler.extract_payload", side_effect=msg_handler.KafkaMsgHandlerError):
            self.assertEqual(msg_handler.handle_message(hccm_msg), (msg_handler.FAILURE_CONFIRM_STATUS, None, None))

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
            "start": datetime.now(),
            "end": datetime.now(),
        }
        with patch("masu.external.kafka_msg_handler._process_report_file") as mock_process:
            msg_handler.process_report("request_id", report_meta)
            mock_process.assert_called()

    @patch("masu.external.kafka_msg_handler._process_report_file", side_effect=NotImplementedError)
    def test_process_report_not_implemented_error(self, _):
        """Test report processing."""
        report_meta = {
            "schema_name": "test_schema",
            "manifest_id": "1",
            "provider_uuid": uuid.uuid4(),
            "provider_type": "OCP",
            "compression": "UNCOMPRESSED",
            "file": "/path/to/file.csv",
            "start": datetime.now(),
            "end": datetime.now(),
        }
        self.assertTrue(msg_handler.process_report("request_id", report_meta))

    def test_summarize_manifest(self):
        """Test report summarization."""
        report_meta = {
            "schema_name": "test_schema",
            "manifest_id": "1",
            "provider_uuid": uuid.uuid4(),
            "provider_type": "OCP",
            "compression": "UNCOMPRESSED",
            "file": "/path/to/file.csv",
            "start": str(datetime.now()),
            "end": str(datetime.now()),
            "ocp_files_to_process": {"filename": {"meta_reportdatestart": str(datetime.now().date())}},
        }

        with patch("masu.external.kafka_msg_handler.MANIFEST_ACCESSOR.manifest_ready_for_summary", return_value=True):
            with patch("masu.external.kafka_msg_handler.summarize_reports.s") as mock_summarize_reports:
                msg_handler.summarize_manifest(report_meta, self.manifest_id)
                mock_summarize_reports.assert_called()

        with patch("masu.external.kafka_msg_handler.MANIFEST_ACCESSOR.manifest_ready_for_summary", return_value=False):
            with patch("masu.external.kafka_msg_handler.summarize_reports.s") as mock_summarize_reports:
                msg_handler.summarize_manifest(report_meta, self.manifest_id)
                mock_summarize_reports.assert_not_called()

    def test_summarize_manifest_dates(self):
        """Test report summarization."""
        start_date = date(year=2024, month=6, day=17)
        end_date = date(year=2024, month=7, day=17)
        report_meta = {
            "schema_name": "test_schema",
            "manifest_id": "1",
            "provider_uuid": uuid.uuid4(),
            "provider_type": "OCP",
            "compression": "UNCOMPRESSED",
            "file": "/path/to/file.csv",
            "start": "2024-07-17 17:00:00.000000",
            "end": "2024-07-17 17:00:00.000000",
            "ocp_files_to_process": {
                "filename1": {"meta_reportdatestart": str(start_date)},
                "filename2": {"meta_reportdatestart": str(end_date)},
            },
        }
        expected_meta = [
            {
                "schema": report_meta.get("schema_name"),
                "schema_name": report_meta.get("schema_name"),
                "provider_type": report_meta.get("provider_type"),
                "provider_uuid": report_meta.get("provider_uuid"),
                "manifest_id": report_meta.get("manifest_id"),
                "start": date(year=2024, month=6, day=17),
                "end": date(year=2024, month=6, day=30),
                "manifest_uuid": "1234",
            },
            {
                "schema": report_meta.get("schema_name"),
                "schema_name": report_meta.get("schema_name"),
                "provider_type": report_meta.get("provider_type"),
                "provider_uuid": report_meta.get("provider_uuid"),
                "manifest_id": report_meta.get("manifest_id"),
                "start": date(year=2024, month=7, day=1),
                "end": date(year=2024, month=7, day=17),
                "manifest_uuid": "1234",
            },
        ]

        with patch("masu.external.kafka_msg_handler.MANIFEST_ACCESSOR.manifest_ready_for_summary", return_value=True):
            with patch("masu.external.kafka_msg_handler.summarize_reports.s") as mock_summarize_reports:
                msg_handler.summarize_manifest(report_meta, self.manifest_id)
                mock_summarize_reports.assert_called_with(expected_meta, OCPQueue.DEFAULT)

        with patch("masu.external.kafka_msg_handler.MANIFEST_ACCESSOR.manifest_ready_for_summary", return_value=False):
            with patch("masu.external.kafka_msg_handler.summarize_reports.s") as mock_summarize_reports:
                msg_handler.summarize_manifest(report_meta, self.manifest_id)
                mock_summarize_reports.assert_not_called()

    def test_summarize_manifest_invalid_dates(self):
        """Test report summarization."""
        table = [
            {
                "name": "missing start and end",
                "start": None,
                "end": None,
                "cr_status": {},
            },
            {
                "name": "invalid start date",
                "start": "0001-01-01 00:00:00+00:00",
                "end": str(datetime.now()),
                "cr_status": {"reports": {"data_collection_message": "it's a bad payload"}},
            },
            {
                "name": "invalid start and end dates",
                "start": "0001-01-01 00:00:00+00:00",
                "end": "0001-01-01 00:00:00+00:00",
                "cr_status": {"reports": {"data_collection_message": "it's a bad payload"}},
            },
        ]

        report_meta = {
            "schema_name": "test_schema",
            "manifest_id": "1",
            "provider_uuid": uuid.uuid4(),
            "provider_type": "OCP",
            "compression": "UNCOMPRESSED",
            "file": "/path/to/file.csv",
        }
        for t in table:
            with self.subTest(test=t.get("name")):
                report_meta["start"] = t.get("start")
                report_meta["end"] = t.get("end")
                report_meta["cr_status"] = t.get("cr_status")

                with patch("masu.external.kafka_msg_handler.summarize_reports.s") as mock_summarize_reports:
                    mock_summarize_reports.assert_not_called()
                    async_id = msg_handler.summarize_manifest(report_meta, self.manifest_id)
                    self.assertIsNone(async_id)

    def test_extract_payload(self):
        """Test to verify extracting payload is successful."""
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"
        with requests_mock.mock() as m:
            m.get(payload_url, content=self.tarball_file)

            fake_dir = tempfile.mkdtemp()
            fake_data_dir = tempfile.mkdtemp()
            with patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir):
                with patch.object(Config, "TMP_DIR", fake_dir):
                    with patch(
                        "masu.external.kafka_msg_handler.utils.get_source_and_provider_from_cluster_id",
                        return_value=self.ocp_source,
                    ):
                        with patch(
                            "masu.external.kafka_msg_handler.create_cost_and_usage_report_manifest", return_value=1
                        ):
                            with patch("masu.external.kafka_msg_handler.record_report_status", returns=None):
                                msg_handler.extract_payload(
                                    payload_url,
                                    "test_request_id",
                                    "fake_identity",
                                    {"account": "1234", "org_id": "5678"},
                                )
                                expected_path = (
                                    f"{Config.INSIGHTS_LOCAL_REPORT_DIR}/{self.cluster_id}/{self.date_range}/"
                                )
                                self.assertTrue(os.path.isdir(expected_path))
                                shutil.rmtree(fake_dir)
                                shutil.rmtree(fake_data_dir)

    @patch("masu.external.kafka_msg_handler.ROSReportShipper")
    def test_extract_payload_ROS_report(self, mock_ros_shipper):
        """Test to verify extracting a ROS payload is successful."""
        ros_file_name = "e6b3701e-1e91-433b-b238-a31e49937558_ROS.csv"
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"
        with requests_mock.mock() as m:
            m.get(payload_url, content=self.ros_tarball_file)
            fake_dir = tempfile.mkdtemp()
            fake_pvc_dir = tempfile.mkdtemp()
            with patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir):
                with patch.object(Config, "TMP_DIR", fake_dir):
                    with patch(
                        "masu.external.kafka_msg_handler.utils.get_source_and_provider_from_cluster_id",
                        return_value=self.ocp_source,
                    ):
                        with patch(
                            "masu.external.kafka_msg_handler.create_cost_and_usage_report_manifest", return_value=1
                        ):
                            with patch("masu.external.kafka_msg_handler.record_report_status", returns=None):
                                msg_handler.extract_payload(
                                    payload_url,
                                    "test_request_id",
                                    "fake_identity",
                                    {"account": "1234", "org_id": "5678"},
                                )
                                mock_ros_shipper.return_value.process_manifest_reports.assert_called_once()
                                # call_args is a tuple of arguments
                                # process_manifest_reports takes a list of tuples and the 1st value is the filename
                                call_args, _ = mock_ros_shipper.return_value.process_manifest_reports.call_args
                                self.assertTrue(call_args[0][0][0], ros_file_name)
                                shutil.rmtree(fake_dir)
                                shutil.rmtree(fake_pvc_dir)

    @patch("masu.external.kafka_msg_handler.ROSReportShipper")
    def test_extract_payload_ROS_report_exception(self, mock_ros_shipper):
        """Test to verify an exception during ROS processing results in a warning log."""
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"
        with requests_mock.mock() as m:
            m.get(payload_url, content=self.ros_tarball_file)
            fake_dir = tempfile.mkdtemp()
            fake_pvc_dir = tempfile.mkdtemp()
            with patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir):
                with patch.object(Config, "TMP_DIR", fake_dir):
                    with patch(
                        "masu.external.kafka_msg_handler.utils.get_source_and_provider_from_cluster_id",
                        return_value=self.ocp_source,
                    ):
                        with patch(
                            "masu.external.kafka_msg_handler.create_cost_and_usage_report_manifest", return_value=1
                        ):
                            with patch("masu.external.kafka_msg_handler.record_report_status", returns=None):
                                mock_ros_shipper.return_value.process_manifest_reports.side_effect = Exception
                                with self.assertLogs(logger="masu.external.kafka_msg_handler", level=logging.WARNING):
                                    msg_handler.extract_payload(
                                        payload_url,
                                        "test_request_id",
                                        "fake_identity",
                                        {"account": "1234", "org_id": "5678"},
                                    )
                                shutil.rmtree(fake_dir)
                                shutil.rmtree(fake_pvc_dir)

    @patch("masu.external.kafka_msg_handler.ROSReportShipper")
    def test_extract_payload_dates(self, _):
        """Test to verify extracting payload is successful."""
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"
        with requests_mock.mock() as m:
            m.get(payload_url, content=self.dates_tarball)

            fake_dir = tempfile.mkdtemp()
            fake_data_dir = tempfile.mkdtemp()
            with patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir):
                with patch.object(Config, "TMP_DIR", fake_dir):
                    with patch(
                        "masu.external.kafka_msg_handler.utils.get_source_and_provider_from_cluster_id",
                        return_value=self.ocp_source,
                    ):
                        with patch(
                            "masu.external.kafka_msg_handler.create_cost_and_usage_report_manifest", return_value=1
                        ):
                            with patch("masu.external.kafka_msg_handler.record_report_status", returns=None):
                                msg_handler.extract_payload(
                                    payload_url,
                                    "test_request_id",
                                    "fake_identity",
                                    {"account": "1234", "org_id": "5678"},
                                )
                                expected_path = (
                                    f"{Config.INSIGHTS_LOCAL_REPORT_DIR}/"
                                    "16b9a60d-0774-4102-9028-bd28d6c38ac2/21230801-21230901"
                                )
                                self.assertTrue(os.path.isdir(expected_path))
                                shutil.rmtree(fake_dir)
                                shutil.rmtree(fake_data_dir)

    def test_extract_payload_no_account(self):
        """Test to verify extracting payload when no provider exists."""
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"
        with requests_mock.mock() as m:
            m.get(payload_url, content=self.tarball_file)

            fake_dir = tempfile.mkdtemp()
            fake_data_dir = tempfile.mkdtemp()
            with patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir):
                with patch.object(Config, "TMP_DIR", fake_dir):
                    with patch(
                        "masu.external.kafka_msg_handler.utils.get_source_and_provider_from_cluster_id",
                        return_value=None,
                    ):
                        self.assertFalse(
                            msg_handler.extract_payload(payload_url, "test_request_id", "fake_identity", {})[0]
                        )
                        shutil.rmtree(fake_dir)
                        shutil.rmtree(fake_data_dir)

    def test_extract_incomplete_file_payload(self):
        """Test to verify extracting payload missing report files is successful."""
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"
        with requests_mock.mock() as m:
            m.get(payload_url, content=self.bad_tarball_file)

            fake_dir = tempfile.mkdtemp()
            fake_data_dir = tempfile.mkdtemp()
            with patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir):
                with patch.object(Config, "TMP_DIR", fake_dir):
                    with patch(
                        "masu.external.kafka_msg_handler.utils.get_source_and_provider_from_cluster_id",
                        return_value=self.ocp_source,
                    ):
                        with patch(
                            "masu.external.kafka_msg_handler.create_cost_and_usage_report_manifest", return_value=1
                        ):
                            with patch("masu.external.kafka_msg_handler.record_report_status"):
                                msg_handler.extract_payload(
                                    payload_url,
                                    "test_request_id",
                                    "fake_identity",
                                    {"account": "1234", "org_id": "5678"},
                                )
                                expected_path = (
                                    f"{Config.INSIGHTS_LOCAL_REPORT_DIR}/{self.cluster_id}/{self.date_range}/"
                                )
                                self.assertFalse(os.path.isdir(expected_path))
                                shutil.rmtree(fake_dir)
                                shutil.rmtree(fake_data_dir)

    def test_extract_payload_outside_retention(self):
        """Test to verify extracting payload is skipped if data is old."""
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"
        with requests_mock.mock() as m:
            m.get(payload_url, content=self.retention_tarball_file)

            fake_dir = tempfile.mkdtemp()
            fake_data_dir = tempfile.mkdtemp()
            with patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir):
                with patch.object(Config, "TMP_DIR", fake_dir):
                    with patch(
                        "masu.external.kafka_msg_handler.utils.get_source_and_provider_from_cluster_id",
                        return_value=self.ocp_source,
                    ):
                        with patch(
                            "masu.external.kafka_msg_handler.create_cost_and_usage_report_manifest", return_value=1
                        ):
                            with patch("masu.external.kafka_msg_handler.record_report_status", returns=None):
                                msg_handler.extract_payload(
                                    payload_url,
                                    "test_request_id",
                                    "fake_identity",
                                    {"account": "1234", "org_id": "5678"},
                                )
                                expected_path = (
                                    f"{Config.INSIGHTS_LOCAL_REPORT_DIR}/{self.cluster_id}/{self.date_range}/"
                                )
                                self.assertFalse(os.path.isdir(expected_path))
                                shutil.rmtree(fake_dir)
                                shutil.rmtree(fake_data_dir)

    def test_extract_no_manifest(self):
        """Test to verify extracting payload missing a manifest is not successful."""
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"
        with requests_mock.mock() as m:
            m.get(payload_url, content=self.no_manifest_file)

            fake_dir = tempfile.mkdtemp()
            fake_data_dir = tempfile.mkdtemp()
            with patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir):
                with patch.object(Config, "TMP_DIR", fake_dir):
                    with patch(
                        "masu.external.kafka_msg_handler.utils.get_source_and_provider_from_cluster_id",
                        return_value=self.ocp_source,
                    ):
                        with patch("masu.external.kafka_msg_handler.create_cost_and_usage_report_manifest", returns=1):
                            with patch("masu.external.kafka_msg_handler.record_report_status"):
                                with self.assertRaises(msg_handler.KafkaMsgHandlerError):
                                    msg_handler.extract_payload(payload_url, "test_request_id", "fake_identity", {})
                                shutil.rmtree(fake_dir)
                                shutil.rmtree(fake_data_dir)

    def test_extract_payload_empty_file_error(self):
        """Test to verify extracting payload with empty file logs warning and continues processing."""
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"
        with requests_mock.mock() as m:
            m.get(payload_url, content=self.empty_file_payload)

            with tempfile.TemporaryDirectory() as fake_dir, tempfile.TemporaryDirectory() as fake_data_dir:
                with (
                    patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir),
                    patch.object(Config, "TMP_DIR", fake_data_dir),
                    patch(
                        "masu.external.kafka_msg_handler.utils.get_source_and_provider_from_cluster_id",
                        return_value=self.ocp_source,
                    ),
                    patch("masu.external.kafka_msg_handler.copy_local_report_file_to_s3_bucket"),
                ):
                    with self.assertLogs(logger="masu.external.kafka_msg_handler", level=logging.WARNING):
                        report_metas, manifest_uuid = msg_handler.extract_payload(
                            payload_url,
                            "test_request_id",
                            "fake_identity",
                            {"account": "1234", "org_id": "5678"},
                        )
                        # Verify that processing continues despite empty file
                        self.assertIsNotNone(manifest_uuid)
                        self.assertTrue(report_metas)

    @patch("masu.external.kafka_msg_handler.TarFile.extractall", side_effect=raise_OSError)
    def test_extract_bad_payload_not_tar(self, mock_extractall):
        """Test to verify extracting payload missing report files is not successful."""
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"
        with requests_mock.mock() as m:
            m.get(payload_url, content=self.bad_tarball_file)

            fake_dir = tempfile.mkdtemp()
            fake_data_dir = tempfile.mkdtemp()
            with patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir):
                with patch.object(Config, "TMP_DIR", fake_dir):
                    with patch(
                        "masu.external.kafka_msg_handler.utils.get_source_and_provider_from_cluster_id",
                        return_value=self.ocp_source,
                    ):
                        with patch("masu.external.kafka_msg_handler.create_cost_and_usage_report_manifest", returns=1):
                            with patch("masu.external.kafka_msg_handler.record_report_status"):
                                with self.assertRaises(msg_handler.KafkaMsgHandlerError):
                                    msg_handler.extract_payload(payload_url, "test_request_id", "fake_identity", {})
                                shutil.rmtree(fake_dir)
                                shutil.rmtree(fake_data_dir)

    def test_extract_payload_bad_url(self):
        """Test to verify extracting payload exceptions are handled."""
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"

        with requests_mock.mock() as m:
            m.get(payload_url, exc=HTTPError)

            with self.assertRaises(msg_handler.KafkaMsgHandlerError):
                msg_handler.extract_payload(payload_url, "test_request_id", "fake_identity", {})

    def test_extract_payload_unable_to_open(self):
        """Test to verify extracting payload exceptions are handled."""
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"

        with requests_mock.mock() as m:
            m.get(payload_url, content=self.tarball_file)
            with patch("masu.external.kafka_msg_handler.Path.write_bytes") as mock_oserror:
                mock_oserror.side_effect = PermissionError
                with self.assertRaises(msg_handler.KafkaMsgHandlerError):
                    msg_handler.extract_payload(payload_url, "test_request_id", "fake_identity", {})

    def test_extract_payload_wrong_file_type(self):
        """Test to verify extracting payload is successful."""
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"

        with requests_mock.mock() as m:
            payload_file = open("./koku/masu/test/data/test_cur.csv", "rb")
            csv_file = payload_file.read()
            payload_file.close()

            m.get(payload_url, content=csv_file)

            with self.assertRaises(msg_handler.KafkaMsgHandlerError):
                msg_handler.extract_payload(payload_url, "test_request_id", "fake_identity", {})

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

    def test_delivery_callback(self):
        """Test that delivery callback raises KafkaMsgHandlerError."""
        msg = "a mock message"
        err = MockError(KafkaError._MSG_TIMED_OUT)
        with self.assertLogs(logger="masu.external.kafka_msg_handler", level=logging.INFO):
            msg_handler.delivery_callback(None, msg)

        with self.assertLogs(logger="masu.external.kafka_msg_handler", level=logging.ERROR):
            msg_handler.delivery_callback(err, msg)

    def test_summarize_manifest_called_with_XL_queue(self):
        """Test report summarization."""
        report_meta = {
            "schema": "test_schema",
            "schema_name": "test_schema",
            "provider_type": "OCP",
            "provider_uuid": uuid.uuid4(),
            "manifest_id": "1",
            "start": str(datetime.now()),
            "end": str(datetime.now()),
            "ocp_files_to_process": {"filename": {"meta_reportdatestart": str(date.today())}},
        }

        # Check when manifest is done
        mock_manifest_accessor = FakeManifest(num_processed_files=2, num_total_files=2)

        with patch("masu.external.kafka_msg_handler.ReportManifestDBAccessor") as mock_accessor:
            mock_accessor.return_value.__enter__.return_value = mock_manifest_accessor
            with patch("masu.external.kafka_msg_handler.summarize_reports.s") as mock_summarize_reports:
                with patch("masu.external.kafka_msg_handler.get_customer_queue", return_value=OCPQueue.XL):
                    msg_handler.summarize_manifest(report_meta, self.manifest_id)
                    self.assertIn(OCPQueue.XL, mock_summarize_reports.call_args.args)

    def test_extract_payload_content_and_process_cr(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = tempfile.NamedTemporaryFile(dir=tmp_dir, delete=False)
            with open(tmp.name, "wb") as f:
                f.write(self.dates_tarball)

            filename = Path(tmp.name)
            manifest, _ = msg_handler.extract_payload_contents(uuid.uuid4().hex, filename, {})
            manifest_path = filename.parent.joinpath(manifest)
            self.assertTrue(os.path.isfile(manifest_path))

            report_meta = utils.parse_manifest(manifest_path.parent)
            self.assertEqual(report_meta.version, "e03142a32dce56bced9dde7963859832129f1a3a")
            self.assertEqual(report_meta.operator_version, "e03142a32dce56bced9dde7963859832129f1a3a")
            cr_data = msg_handler.process_cr(report_meta, {})
            self.assertEqual(cr_data["operator_version"], "e03142a32dce56bced9dde7963859832129f1a3a")

            report_meta.version = "b5a2c05255069215eb564dcc5c4ec6ca4b33325d"
            report_meta = utils.Manifest.model_validate(report_meta.model_dump())
            self.assertEqual(report_meta.operator_version, "costmanagement-metrics-operator:3.0.1")
            cr_data = msg_handler.process_cr(report_meta, {})
            self.assertEqual(cr_data["operator_version"], "costmanagement-metrics-operator:3.0.1")

            # test that we warn when basic auth is being used:
            report_meta.cr_status["authentication"]["type"] = "basic"
            with self.assertLogs(logger="masu.external.kafka_msg_handler", level=logging.INFO) as log:
                msg_handler.process_cr(report_meta, {})
                self.assertEqual(len(log.output), 2)
                self.assertIn("cluster is using basic auth", log.output[1])

    def test_create_cost_and_usage_report_manifest(self):
        manifest = Path("koku/masu/test/data/ocp/payload2/manifest.json")
        report_meta = utils.parse_manifest(manifest.parent)
        manifest_id = msg_handler.create_cost_and_usage_report_manifest(self.ocp_provider_uuid, report_meta, {})
        manifest = CostUsageReportManifest.objects.get(id=manifest_id)
        self.assertEqual(manifest.assembly_id, str(report_meta.uuid))
        self.assertEqual(manifest.export_datetime, report_meta.date)
        self.assertEqual(manifest.operator_version, "e03142a32dce56bced9dde7963859832129f1a3a")

    def test_divide_csv_daily(self):
        """Test the divide_csv_daily method."""
        with tempfile.TemporaryDirectory() as td:
            filename = "storage_data.csv"
            file_path = Path(td, filename)
            with patch("masu.external.kafka_msg_handler.pd") as mock_pd:
                with patch(
                    "masu.external.kafka_msg_handler.utils.detect_type",
                    return_value=("storage_usage", None),
                ):
                    dates = ["2020-01-01 00:00:00 +UTC", "2020-01-02 00:00:00 +UTC"]
                    hour_dict = {"2020-01-01": 1, "2020-01-02": 1}
                    mock_report = {
                        "interval_start": dates,
                        "persistentvolumeclaim_labels": ["label1", "label2"],
                    }
                    df = pd.DataFrame(data=mock_report)
                    mock_pd.read_csv.return_value = df
                    daily_files = msg_handler.divide_csv_daily(file_path, self.ocp_manifest_id, hour_dict)
                    self.assertNotEqual([], daily_files)
                    self.assertEqual(len(daily_files), 2)
                    gen_files = [
                        f"storage_usage.2020-01-01.{self.ocp_manifest_id}.0.csv",
                        f"storage_usage.2020-01-02.{self.ocp_manifest_id}.0.csv",
                    ]
                    expected_dates = [datetime.strptime(date[:10], "%Y-%m-%d") for date in dates]
                    expected = [
                        {"filepath": Path(td, gen_file), "date": expected_dates[i], "num_hours": 1}
                        for i, gen_file in enumerate(gen_files)
                    ]
                    for expected_item in expected:
                        self.assertIn(expected_item, daily_files)

    def test_get_data_frame_no_tokenizing_error(self):
        """Test get_data_frame does not raise Tokenizing error when reading files."""

        file_paths = [
            Path("./koku/masu/test/data/ocp/valid-csv.csv"),
            Path("./koku/masu/test/data/ocp/tokenizing-error.csv"),
        ]
        for file_path in file_paths:
            try:
                msg_handler.get_data_frame(file_path)
            except Exception:
                self.fail(f"failed to read: {file_path}")

    def test_get_data_frame_empty_file_error(self):
        """Test get_data_frame raises EmptyPayloadFileError when file is empty."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create an empty CSV file
            empty_file_path = Path(tmp_dir, "empty_file.csv")
            empty_file_path.touch()  # Creates empty file

            # Test that EmptyPayloadFileError is raised
            with self.assertRaises(EmptyPayloadFileError) as context:
                msg_handler.get_data_frame(empty_file_path)

            # Verify the error message
            self.assertEqual(str(context.exception), "File is empty.")

    @patch("masu.external.kafka_msg_handler.os")
    @patch("masu.external.kafka_msg_handler.copy_local_report_file_to_s3_bucket")
    @patch("masu.external.kafka_msg_handler.divide_csv_daily")
    def test_create_daily_archives_very_old_operator(self, mock_divide, *args):
        """Test that this method returns a file list."""
        # modify the manifest to remove the operator version to test really old operators:
        self.ocp_manifest.operator_version = None
        self.ocp_manifest.save()

        daily_files = [
            {"filepath": FILE_PATH_ONE, "date": datetime.fromisoformat("2020-01-01"), "num_hours": 1},
            {"filepath": FILE_PATH_TWO, "date": datetime.fromisoformat("2020-01-01"), "num_hours": 1},
        ]
        expected_filenames = [FILE_PATH_ONE, FILE_PATH_TWO]

        mock_divide.return_value = daily_files

        file_path = Path("path")
        result = msg_handler.create_daily_archives(self.fake_payload_info, file_path, {})

        self.assertCountEqual(result.keys(), expected_filenames)

    @patch("masu.external.kafka_msg_handler.os")
    @patch("masu.external.kafka_msg_handler.copy_local_report_file_to_s3_bucket")
    def test_create_daily_archives_non_daily_operator_files(self, *args):
        """Test that this method returns a file list."""
        file_path = Path("path")

        context = {"version": "1"}
        expected = [file_path]
        result = msg_handler.create_daily_archives(self.fake_payload_info, file_path, context)
        self.assertCountEqual(result.keys(), expected)

    @patch("masu.external.kafka_msg_handler.os")
    @patch("masu.external.kafka_msg_handler.copy_local_report_file_to_s3_bucket")
    @patch("masu.external.kafka_msg_handler.divide_csv_daily")
    def test_create_daily_archives_daily_operator_files(self, mock_divide, *args):
        """Test that this method returns a file list."""
        self.ocp_manifest.operator_daily_reports = True
        self.ocp_manifest.save()

        daily_files = [
            {"filepath": FILE_PATH_ONE, "date": datetime.fromisoformat("2020-01-01"), "num_hours": 23},
            {"filepath": FILE_PATH_TWO, "date": datetime.fromisoformat("2020-01-02"), "num_hours": 24},
        ]
        expected_filenames = [FILE_PATH_ONE, FILE_PATH_TWO]
        expected_result = {
            FILE_PATH_ONE: {"meta_reportdatestart": "2020-01-01", "meta_reportnumhours": "23"},
            FILE_PATH_TWO: {"meta_reportdatestart": "2020-01-02", "meta_reportnumhours": "24"},
        }

        mock_divide.return_value = daily_files

        file_path = Path("path")
        result = msg_handler.create_daily_archives(self.fake_payload_info, file_path, {})

        self.assertCountEqual(result.keys(), expected_filenames)
        self.assertDictEqual(result, expected_result)

    @patch("masu.external.kafka_msg_handler.os")
    @patch("masu.external.kafka_msg_handler.copy_local_report_file_to_s3_bucket")
    @patch("masu.external.kafka_msg_handler.divide_csv_daily")
    def test_create_daily_archives_daily_operator_files_empty_file(self, mock_divide, *args):
        """Test that this method returns a file list."""
        self.ocp_manifest.operator_daily_reports = True
        self.ocp_manifest.save()

        start_date = self.dh.this_month_start
        self.fake_payload_info.manifest.date = start_date

        # simulate empty report file
        mock_divide.return_value = None

        file_path = Path("path")
        expected_result = {
            file_path: {"meta_reportdatestart": str(start_date.date()), "meta_reportnumhours": "0"},
        }

        result = msg_handler.create_daily_archives(self.fake_payload_info, file_path, {})

        self.assertCountEqual(result.keys(), [file_path])
        self.assertDictEqual(result, expected_result)

    def test_divide_csv_daily_leading_zeros(self):
        """Test if the divide_csv_daily method will keep the leading zeros."""

        with tempfile.TemporaryDirectory() as td:
            filename = "storage_data.csv"
            file_path = Path(td, filename)
            with patch("masu.external.kafka_msg_handler.pd") as mock_pd:
                with patch(
                    "masu.external.kafka_msg_handler.utils.detect_type",
                    return_value=("storage_usage", None),
                ):
                    dates = ["2020-01-01 00:00:00 +UTC", "2020-01-02 00:00:00 +UTC"]
                    mock_report = {
                        "interval_start": dates,
                        "persistentvolumeclaim_labels": ["0099999999999", "0099999999999"],
                    }
                    df = pd.DataFrame(data=mock_report)
                    mock_pd.read_csv.return_value = df
                    daily_files = msg_handler.divide_csv_daily(file_path, self.ocp_manifest_id, {})

                    for daily_file in daily_files:
                        with open(str(daily_file["filepath"])) as file:
                            csv = file.readlines()

                        self.assertIn("0099999999999", csv[1])
