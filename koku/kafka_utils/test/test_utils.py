#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Kafka utils."""
from unittest import TestCase
from unittest.mock import patch

from kafka_utils import utils
from masu.prometheus_stats import WORKER_REGISTRY


class KafkaUtilsTest(TestCase):
    """Test Cases for the Kafka utilities."""

    def test_check_kafka_connection(self):
        """Test check kafka connections."""
        with patch("kafka.BrokerConnection.connect_blocking", return_value=False):
            result = utils.check_kafka_connection()
            self.assertFalse(result)
        with patch("kafka.BrokerConnection.connect_blocking", return_value=True):
            with patch("kafka.BrokerConnection.close") as mock_close:
                result = utils.check_kafka_connection()
                mock_close.assert_called()
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
