#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Kafka utils."""
from unittest import TestCase
from unittest.mock import patch

from kafka_utils import utils
from koku.configurator import EnvConfigurator
from koku.configurator import KafkaSASLConfig
from masu.prometheus_stats import WORKER_REGISTRY


class KafkaUtilsTest(TestCase):
    """Test Cases for the Kafka utilities."""

    def test_check_kafka_connection(self):
        """Test check kafka connections."""
        with patch("kafka_utils.utils.get_admin_client") as mock_client:
            mock_client.return_value.list_topics.return_value.topics = []
            result = utils.check_kafka_connection()
            self.assertFalse(result)
        with patch("kafka_utils.utils.get_admin_client") as mock_client:
            mock_client.return_value.list_topics.return_value.topics = [1]
            result = utils.check_kafka_connection()
            self.assertTrue(result)

    @patch("time.sleep", side_effect=None)
    @patch("kafka_utils.utils.check_kafka_connection", side_effect=[bool(0), bool(1)])
    def test_kafka_connection_metrics_listen_for_messages(self, mock_start, mock_sleep):
        """Test check_kafka_connection increments kafka connection errors on KafkaError."""
        connection_errors_before = WORKER_REGISTRY.get_sample_value("kafka_connection_errors_total")
        utils.is_kafka_connected()
        connection_errors_after = WORKER_REGISTRY.get_sample_value("kafka_connection_errors_total")
        self.assertEqual(connection_errors_after - connection_errors_before, 1)

    def test_extract_from_header(self):
        """Test test_extract_from_header."""
        encoded_value = bytes("value", "utf-8")
        test_table = [
            {
                "test": [
                    ["key", encoded_value],
                ],
                "key": "key",
                "expected": "value",
            },
            {
                "test": [
                    ["key", None],
                ],
                "key": "key",
                "expected": None,
            },
            {
                "test": None,
                "key": "key",
                "expected": None,
            },
            {
                "test": [["not-key", encoded_value], ["not-key-2", encoded_value]],
                "key": "key",
                "expected": None,
            },
        ]
        for test in test_table:
            with self.subTest(test=test):
                result = utils.extract_from_header(test["test"], test["key"])
                self.assertEqual(result, test["expected"])


class ProducerSingletonTest(TestCase):
    def test_producer_singleton(self):
        """Tests that the ID of two created ProducerSingletons are in fact the same whereas two Producers are not."""
        # no provided bootstrap.servers create a producer that doesn't connect to anything.
        pfake = utils.Producer({})
        pfake2 = utils.Producer({})
        self.assertNotEqual(id(pfake), id(pfake2))
        p1 = utils.ProducerSingleton({})
        p2 = utils.ProducerSingleton({})
        self.assertEqual(id(p1), id(p2))


class AdminClientSingletonTest(TestCase):
    def test_producer_singleton(self):
        """Tests that the ID of two created ProducerSingletons are in fact the same whereas two Producers are not."""
        # no provided bootstrap.servers create a producer that doesn't connect to anything.
        pfake = utils.AdminClient({})
        pfake2 = utils.AdminClient({})
        self.assertNotEqual(id(pfake), id(pfake2))
        p1 = utils.AdminClientSingleton({})
        p2 = utils.AdminClientSingleton({})
        self.assertEqual(id(p1), id(p2))


class EnvConfiguratorKafkaSASLTest(TestCase):
    """Test EnvConfigurator Kafka SASL/TLS methods."""

    @patch.dict(
        "os.environ",
        {
            "KAFKA_SASL_MECHANISM": "SCRAM-SHA-512",
            "KAFKA_SASL_USERNAME": "user1",
            "KAFKA_SASL_PASSWORD": "pass1",
            "KAFKA_SECURITY_PROTOCOL": "SASL_SSL",
        },
    )
    def test_get_kafka_sasl_with_env_vars(self):
        """EnvConfigurator returns KafkaSASLConfig when KAFKA_SASL_MECHANISM is set."""
        result = EnvConfigurator.get_kafka_sasl()
        self.assertIsInstance(result, KafkaSASLConfig)
        self.assertEqual(result.saslMechanism, "SCRAM-SHA-512")
        self.assertEqual(result.username, "user1")
        self.assertEqual(result.password, "pass1")
        self.assertEqual(result.securityProtocol, "SASL_SSL")

    @patch.dict("os.environ", {}, clear=True)
    def test_get_kafka_sasl_without_env_vars(self):
        """EnvConfigurator returns empty dict when no SASL env vars are set."""
        result = EnvConfigurator.get_kafka_sasl()
        self.assertEqual(result, {})
        self.assertFalse(result)

    @patch.dict("os.environ", {"KAFKA_SASL_MECHANISM": "PLAIN"})
    def test_get_kafka_sasl_defaults_security_protocol(self):
        """EnvConfigurator defaults securityProtocol to SASL_SSL."""
        result = EnvConfigurator.get_kafka_sasl()
        self.assertEqual(result.securityProtocol, "SASL_SSL")

    @patch.dict("os.environ", {"KAFKA_SSL_CA_LOCATION": "/etc/kafka/certs/ca.crt"})
    def test_get_kafka_cacert_with_env_var(self):
        """EnvConfigurator returns CA cert path when set."""
        result = EnvConfigurator.get_kafka_cacert()
        self.assertEqual(result, "/etc/kafka/certs/ca.crt")

    @patch.dict("os.environ", {}, clear=True)
    def test_get_kafka_cacert_without_env_var(self):
        """EnvConfigurator returns None when no CA cert path is set."""
        result = EnvConfigurator.get_kafka_cacert()
        self.assertIsNone(result)

    @patch.dict("os.environ", {"KAFKA_SASL_MECHANISM": "SCRAM-SHA-512"})
    def test_get_kafka_authtype_with_sasl(self):
        """EnvConfigurator returns 'sasl' when mechanism is set."""
        result = EnvConfigurator.get_kafka_authtype()
        self.assertEqual(result, "sasl")

    @patch.dict("os.environ", {}, clear=True)
    def test_get_kafka_authtype_without_sasl(self):
        """EnvConfigurator returns None when no mechanism is set."""
        result = EnvConfigurator.get_kafka_authtype()
        self.assertIsNone(result)
