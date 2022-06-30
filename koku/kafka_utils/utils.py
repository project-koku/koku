#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common utility functions for Kafka implementations."""
import logging
import random
import socket
import time

from confluent_kafka import Consumer
from confluent_kafka import Producer
from kafka import BrokerConnection

from masu.config import Config
from masu.prometheus_stats import KAFKA_CONNECTION_ERRORS_COUNTER

LOG = logging.getLogger(__name__)


def get_consumer(topic, address):  # pragma: no cover
    """Create a Kafka consumer."""
    consumer = Consumer(
        {
            "bootstrap.servers": address,
            "group.id": "hccm-group",
            "queued.max.messages.kbytes": 1024,
            "enable.auto.commit": False,
            "max.poll.interval.ms": 1080000,  # 18 minutes
        },
        logger=LOG,
    )
    consumer.subscribe([topic])
    return consumer


def get_producer():  # pragma: no cover
    """Create a Kafka producer."""
    producer = Producer({"bootstrap.servers": Config.INSIGHTS_KAFKA_ADDRESS, "message.timeout.ms": 1000})
    return producer


def delivery_callback(err, msg):
    """Acknowledge message success or failure."""
    if err is not None:
        LOG.error(f"Failed to deliver message: {msg}: {err}")
    else:
        LOG.info("kafka message delivered.")


def backoff(interval, maximum=120):
    """Exponential back-off."""
    wait = min(maximum, (2**interval)) + random.random()
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
            LOG.error(f"Unable to connect to Kafka server: {host}:{port}")
            KAFKA_CONNECTION_ERRORS_COUNTER.inc()
            backoff(count)
            count += 1
    return result
