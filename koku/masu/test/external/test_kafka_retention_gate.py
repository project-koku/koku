#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the per-tenant Kafka retention gate."""
import shutil
import tempfile
from unittest.mock import patch

import requests_mock

import masu.external.kafka_msg_handler as msg_handler
from masu.config import Config
from masu.test import MasuTestCase


class KafkaRetentionGateTest(MasuTestCase):
    """Tests that extract_payload uses per-tenant retention for the Kafka gate."""

    def setUp(self):
        super().setUp()
        with open("./koku/masu/test/data/ocp/outside_retention_payload.tar.gz", "rb") as f:
            self.retention_tarball_file = f.read()
        with open("./koku/masu/test/data/ocp/payload.tar.gz", "rb") as f:
            self.tarball_file = f.read()
        from model_bakery import baker

        self.ocp_source = baker.make("Sources", provider=self.ocp_provider, org_id=self.org_id)

    def test_kafka_handler_imports_get_data_retention_months(self):
        """Verify the kafka msg handler imports the per-tenant helper."""
        from masu.external import kafka_msg_handler

        self.assertTrue(
            hasattr(kafka_msg_handler, "get_data_retention_months"),
            "kafka_msg_handler should import get_data_retention_months",
        )

    @patch("masu.external.kafka_msg_handler.record_report_status", returns=None)
    @patch("masu.external.kafka_msg_handler.create_cost_and_usage_report_manifest", return_value=1)
    @patch("masu.external.kafka_msg_handler.utils.get_source_and_provider_from_cluster_id")
    def test_extract_payload_calls_get_data_retention_months(self, mock_source, *_):
        """extract_payload reads per-tenant retention via get_data_retention_months."""
        mock_source.return_value = self.ocp_source
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"

        with requests_mock.mock() as m:
            m.get(payload_url, content=self.retention_tarball_file)
            fake_dir = tempfile.mkdtemp()
            try:
                with (
                    patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir),
                    patch.object(Config, "TMP_DIR", fake_dir),
                    patch(
                        "masu.external.kafka_msg_handler.get_data_retention_months",
                        return_value=Config.MASU_RETAIN_NUM_MONTHS,
                    ) as mock_retention,
                ):
                    msg_handler.extract_payload(
                        payload_url,
                        "test_request_id",
                        "fake_identity",
                        {"account": "1234", "org_id": self.org_id},
                    )
                    mock_retention.assert_called_once()
                    call_schema = mock_retention.call_args[0][0]
                    self.assertEqual(call_schema, self.schema_name)
            finally:
                shutil.rmtree(fake_dir, ignore_errors=True)

    @patch("masu.external.kafka_msg_handler.record_report_status", returns=None)
    @patch("masu.external.kafka_msg_handler.create_cost_and_usage_report_manifest", return_value=1)
    @patch("masu.external.kafka_msg_handler.utils.get_source_and_provider_from_cluster_id")
    def test_extract_payload_uses_config_fallback_when_helper_returns_none(self, mock_source, *_):
        """When get_data_retention_months returns None, Kafka gate falls back to Config."""
        mock_source.return_value = self.ocp_source
        payload_url = "http://insights-upload.com/quarnantine/file_to_validate"

        with requests_mock.mock() as m:
            m.get(payload_url, content=self.retention_tarball_file)
            fake_dir = tempfile.mkdtemp()
            try:
                with (
                    patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir),
                    patch.object(Config, "TMP_DIR", fake_dir),
                    patch(
                        "masu.external.kafka_msg_handler.get_data_retention_months",
                        return_value=None,
                    ) as mock_retention,
                ):
                    msg_handler.extract_payload(
                        payload_url,
                        "test_request_id",
                        "fake_identity",
                        {"account": "1234", "org_id": self.org_id},
                    )
                    mock_retention.assert_called_once()
            finally:
                shutil.rmtree(fake_dir, ignore_errors=True)
