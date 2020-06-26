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
"""Common utility functions for Kafka implementations."""
import logging
import random
import socket
import time

from kafka import BrokerConnection

from masu.prometheus_stats import KAFKA_CONNECTION_ERRORS_COUNTER


LOG = logging.getLogger(__name__)


def backoff(interval, maximum=120):
    """Exponential back-off."""
    wait = min(maximum, (2 ** interval)) + random.random()
    LOG.info("Sleeping for %.2f seconds.", wait)
    time.sleep(wait)


def check_kafka_connection(host, port):
    """Check connectability of Kafka Broker."""
    conn = BrokerConnection(host, int(port), socket.AF_UNSPEC)
    connected = conn.connect_blocking(timeout=1)
    if connected:
        conn.close()
    return connected


def is_kafka_connected(host, port):
    """Wait for Kafka to become available."""
    count = 0
    result = False
    while not result:
        result = check_kafka_connection(host, port)
        if result:
            LOG.info("Test connection to Kafka was successful.")
        else:
            LOG.error("Unable to connect to Kafka server.")
            KAFKA_CONNECTION_ERRORS_COUNTER.inc()
            backoff(count)
            count += 1
    return result
