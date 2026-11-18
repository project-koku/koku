#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Kafka publisher module."""
import json
from unittest.mock import MagicMock
from unittest.mock import patch

from django.test import TestCase

from api.provider.models import Sources
from sources.api.source_type_mapping import COST_MGMT_APP_TYPE_ID
from sources.kafka_publisher import _build_kafka_headers
from sources.kafka_publisher import _get_message_key_from_headers
from sources.kafka_publisher import publish_application_destroy_event


class BuildKafkaHeadersTest(TestCase):
    """Test Cases for _build_kafka_headers."""

    def _create_mock_source(self, account_id=None, org_id=None, auth_header=None, source_id=1):
        """Create a mock Sources object."""
        source = MagicMock(spec=Sources)
        source.source_id = source_id
        source.account_id = account_id
        source.org_id = org_id
        source.auth_header = auth_header
        return source

    def test_build_headers_all_fields(self):
        """Test building headers with all fields populated."""
        source = self._create_mock_source(
            account_id="12345",
            org_id="org67890",
            auth_header="encoded-identity-header",
        )
        headers = _build_kafka_headers(source, "Application.destroy")

        self.assertIn(("event_type", b"Application.destroy"), headers)
        self.assertIn(("encoding", b"json"), headers)
        self.assertIn(("x-rh-sources-account-number", b"12345"), headers)
        self.assertIn(("x-rh-sources-org-id", b"org67890"), headers)
        self.assertIn(("x-rh-identity", b"encoded-identity-header"), headers)
        self.assertEqual(len(headers), 5)

    def test_build_headers_no_optional_fields(self):
        """Test building headers with only required fields."""
        source = self._create_mock_source(account_id=None, org_id=None, auth_header=None)
        headers = _build_kafka_headers(source, "Application.destroy")

        self.assertIn(("event_type", b"Application.destroy"), headers)
        self.assertIn(("encoding", b"json"), headers)
        self.assertEqual(len(headers), 2)

    def test_build_headers_only_account_id(self):
        """Test building headers with only account_id."""
        source = self._create_mock_source(account_id="12345")
        headers = _build_kafka_headers(source, "Application.destroy")

        self.assertIn(("x-rh-sources-account-number", b"12345"), headers)
        self.assertEqual(len(headers), 3)

    def test_build_headers_only_org_id(self):
        """Test building headers with only org_id."""
        source = self._create_mock_source(org_id="org67890")
        headers = _build_kafka_headers(source, "Application.destroy")

        self.assertIn(("x-rh-sources-org-id", b"org67890"), headers)
        self.assertEqual(len(headers), 3)

    def test_build_headers_only_auth_header(self):
        """Test building headers with only auth_header."""
        source = self._create_mock_source(auth_header="identity-header")
        headers = _build_kafka_headers(source, "Application.destroy")

        self.assertIn(("x-rh-identity", b"identity-header"), headers)
        self.assertEqual(len(headers), 3)


class GetMessageKeyFromHeadersTest(TestCase):
    """Test Cases for _get_message_key_from_headers."""

    def test_precedence_org_id_first(self):
        """Test that org_id has highest precedence."""
        headers = [
            ("event_type", b"Application.destroy"),
            ("x-rh-sources-account-number", b"account-123"),
            ("x-rh-sources-org-id", b"org-456"),
            ("x-rh-identity", b"identity-789"),
        ]
        key = _get_message_key_from_headers(headers, source_id=1)
        self.assertEqual(key, "org-456")

    def test_precedence_account_number_second(self):
        """Test that account_number has second precedence."""
        headers = [
            ("event_type", b"Application.destroy"),
            ("x-rh-sources-account-number", b"account-123"),
            ("x-rh-identity", b"identity-789"),
        ]
        key = _get_message_key_from_headers(headers, source_id=1)
        self.assertEqual(key, "account-123")

    def test_precedence_identity_third(self):
        """Test that x-rh-identity has third precedence."""
        headers = [
            ("event_type", b"Application.destroy"),
            ("x-rh-identity", b"identity-789"),
        ]
        key = _get_message_key_from_headers(headers, source_id=1)
        self.assertEqual(key, "identity-789")

    def test_fallback_to_source_id(self):
        """Test fallback to source_id when no identity headers present."""
        headers = [
            ("event_type", b"Application.destroy"),
            ("encoding", b"json"),
        ]
        key = _get_message_key_from_headers(headers, source_id=42)
        self.assertEqual(key, "42")

    def test_empty_headers_fallback(self):
        """Test fallback with empty headers list."""
        key = _get_message_key_from_headers([], source_id=99)
        self.assertEqual(key, "99")


class PublishApplicationDestroyEventTest(TestCase):
    """Test Cases for publish_application_destroy_event."""

    def _create_mock_source(self, source_id=1, org_id="org123", account_id="acct456", auth_header="header"):
        """Create a mock Sources object."""
        source = MagicMock(spec=Sources)
        source.source_id = source_id
        source.org_id = org_id
        source.account_id = account_id
        source.auth_header = auth_header
        return source

    @patch("sources.kafka_publisher.get_producer")
    def test_publish_success(self, mock_get_producer):
        """Test successful event publishing."""
        mock_producer = MagicMock()
        mock_get_producer.return_value = mock_producer

        source = self._create_mock_source(source_id=10, org_id="org123")
        publish_application_destroy_event(source)

        mock_producer.produce.assert_called_once()
        call_kwargs = mock_producer.produce.call_args

        # Verify the message value contains expected payload
        message_value = call_kwargs.kwargs.get("value") or call_kwargs[1].get("value")
        payload = json.loads(message_value.decode("utf-8"))
        self.assertEqual(payload["Source_id"], 10)
        self.assertEqual(payload["Application_type_id"], int(COST_MGMT_APP_TYPE_ID))
        self.assertEqual(payload["Tenant"], "org123")

        mock_producer.poll.assert_called_once_with(0)

    @patch("sources.kafka_publisher.get_producer")
    def test_publish_uses_account_id_when_no_org_id(self, mock_get_producer):
        """Test that account_id is used as Tenant when org_id is not available."""
        mock_producer = MagicMock()
        mock_get_producer.return_value = mock_producer

        source = self._create_mock_source(source_id=10, org_id=None, account_id="acct456")
        publish_application_destroy_event(source)

        call_kwargs = mock_producer.produce.call_args
        message_value = call_kwargs.kwargs.get("value") or call_kwargs[1].get("value")
        payload = json.loads(message_value.decode("utf-8"))
        self.assertEqual(payload["Tenant"], "acct456")

    @patch("sources.kafka_publisher.get_producer")
    def test_publish_handles_exception(self, mock_get_producer):
        """Test that exceptions are caught and logged, not raised."""
        mock_get_producer.side_effect = Exception("Kafka connection failed")

        source = self._create_mock_source()
        # Should not raise
        publish_application_destroy_event(source)

    @patch("sources.kafka_publisher.get_producer")
    def test_publish_produce_exception(self, mock_get_producer):
        """Test that producer.produce() exceptions are caught."""
        mock_producer = MagicMock()
        mock_producer.produce.side_effect = Exception("Produce failed")
        mock_get_producer.return_value = mock_producer

        source = self._create_mock_source()
        # Should not raise
        publish_application_destroy_event(source)

    @patch("sources.kafka_publisher.get_producer")
    def test_publish_headers_include_identity(self, mock_get_producer):
        """Test that published message includes correct headers."""
        mock_producer = MagicMock()
        mock_get_producer.return_value = mock_producer

        source = self._create_mock_source(
            source_id=5,
            org_id="org-test",
            account_id="acct-test",
            auth_header="identity-header",
        )
        publish_application_destroy_event(source)

        call_kwargs = mock_producer.produce.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")

        header_dict = {k: v for k, v in headers}
        self.assertEqual(header_dict["event_type"], b"Application.destroy")
        self.assertEqual(header_dict["x-rh-sources-org-id"], b"org-test")
        self.assertEqual(header_dict["x-rh-sources-account-number"], b"acct-test")
        self.assertEqual(header_dict["x-rh-identity"], b"identity-header")

    @patch("sources.kafka_publisher.get_producer")
    def test_publish_message_key_uses_org_id(self, mock_get_producer):
        """Test that message key uses org_id (highest precedence)."""
        mock_producer = MagicMock()
        mock_get_producer.return_value = mock_producer

        source = self._create_mock_source(org_id="org-key-test", account_id="acct-key-test")
        publish_application_destroy_event(source)

        call_kwargs = mock_producer.produce.call_args
        message_key = call_kwargs.kwargs.get("key") or call_kwargs[1].get("key")
        self.assertEqual(message_key, "org-key-test")
