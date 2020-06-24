#
# Copyright 2020 Red Hat, Inc.
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
"""Test Kafka utils."""
from unittest import TestCase
from unittest.mock import patch

from kafka_utils import utils
from masu.prometheus_stats import WORKER_REGISTRY

TEST_HOST = "fake-host"
TEST_PORT = "0000"


class KafkaUtilsTest(TestCase):
    """Test Cases for the Kafka utilities."""

    def test_check_kafka_connection(self):
        """Test check kafka connections."""
        with patch("kafka.BrokerConnection.connect_blocking", return_value=False):
            result = utils.check_kafka_connection(TEST_HOST, TEST_PORT)
            self.assertFalse(result)
        with patch("kafka.BrokerConnection.connect_blocking", return_value=True):
            with patch("kafka.BrokerConnection.close") as mock_close:
                result = utils.check_kafka_connection(TEST_HOST, TEST_PORT)
                mock_close.assert_called()
                self.assertTrue(result)

    @patch("time.sleep", side_effect=None)
    @patch("kafka_utils.utils.check_kafka_connection", side_effect=[bool(0), bool(1)])
    def test_kafka_connection_metrics_listen_for_messages(self, mock_start, mock_sleep):
        """Test check_kafka_connection increments kafka connection errors on KafkaError."""
        connection_errors_before = WORKER_REGISTRY.get_sample_value("kafka_connection_errors_total")
        utils.is_kafka_connected(TEST_HOST, TEST_PORT)
        connection_errors_after = WORKER_REGISTRY.get_sample_value("kafka_connection_errors_total")
        self.assertEqual(connection_errors_after - connection_errors_before, 1)
