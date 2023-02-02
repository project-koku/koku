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


def _get_managed_kafka_config(conf=None):  # pragma: no cover
    """Create/Update a dict with managed Kafka configuration"""
    if not isinstance(conf, dict):
        conf = {}

    if Config.INSIGHTS_KAFKA_SASL:
        conf["security.protocol"] = Config.INSIGHTS_KAFKA_SASL.securityProtocol
        conf["sasl.mechanisms"] = Config.INSIGHTS_KAFKA_SASL.saslMechanism
        conf["sasl.username"] = Config.INSIGHTS_KAFKA_SASL.username
        conf["sasl.password"] = Config.INSIGHTS_KAFKA_SASL.password

    if Config.INSIGHTS_KAFKA_CACERT:
        conf["ssl.ca.location"] = Config.INSIGHTS_KAFKA_CACERT

    return conf


def _get_consumer_config(address, conf_settings):  # pragma: no cover
    """Get the default consumer config"""
    conf = {
        "bootstrap.servers": address,
        "api.version.request": False,
        "broker.version.fallback": "0.10.2",
    }
    conf = _get_managed_kafka_config(conf)
    conf.update(conf_settings)

    return conf


def get_consumer(conf_settings, address=Config.INSIGHTS_KAFKA_ADDRESS):  # pragma: no cover
    """Create a Kafka consumer."""
    conf = _get_consumer_config(address, conf_settings)
    LOG.info(f"Consumer config {conf}")
    return Consumer(conf, logger=LOG)


def _get_producer_config(address, conf_settings):  # pragma: no cover
    """Return Kafka Producer config"""
    producer_conf = {"bootstrap.servers": address, "message.timeout.ms": 1000}
    producer_conf = _get_managed_kafka_config(producer_conf)
    producer_conf.update(conf_settings)

    return producer_conf


def get_producer(conf_settings=None, address=Config.INSIGHTS_KAFKA_ADDRESS):  # pragma: no cover
    """Create a Kafka producer."""
    if conf_settings is None:
        conf_settings = {}
    conf = _get_producer_config(address, conf_settings)
    return Producer(conf)


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


def extract_from_header(headers, header_type):
    """Retrieve information from Kafka Headers."""
    LOG.debug(f"[extract_from_header] extracting `{header_type}` from headers: {headers}")
    if headers is None:
        return
    for header in headers:
        if header_type in header:
            for item in header:
                if item == header_type or item is None:
                    continue
                else:
                    return item.decode("ascii")
    return
