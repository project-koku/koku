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

from koku.configurator import CONFIGURATOR
from masu.prometheus_stats import KAFKA_CONNECTION_ERRORS_COUNTER
from masu.util.common import SingletonMeta


LOG = logging.getLogger(__name__)
UPLOAD_TOPIC = CONFIGURATOR.get_kafka_topic("platform.upload.announce")
VALIDATION_TOPIC = CONFIGURATOR.get_kafka_topic("platform.upload.validation")
NOTIFICATION_TOPIC = CONFIGURATOR.get_kafka_topic("platform.notifications.ingress")
ROS_TOPIC = CONFIGURATOR.get_kafka_topic("hccm.ros.events")
SUBS_TOPIC = CONFIGURATOR.get_kafka_topic("platform.rhsm-subscriptions.service-instance-ingress")
SOURCES_TOPIC = CONFIGURATOR.get_kafka_topic("platform.sources.event-stream")


class ProducerSingleton(Producer, metaclass=SingletonMeta):
    """Creates a singleton instance of a Kafka Producer"""


def _get_managed_kafka_config(conf=None):  # pragma: no cover
    """Create/Update a dict with managed Kafka configuration"""
    if not isinstance(conf, dict):
        conf = {}

    conf["bootstrap.servers"] = ",".join(CONFIGURATOR.get_kafka_broker_list())

    if sasl := CONFIGURATOR.get_kafka_sasl():
        conf["security.protocol"] = sasl.securityProtocol
        conf["sasl.mechanisms"] = sasl.saslMechanism
        conf["sasl.username"] = sasl.username
        conf["sasl.password"] = sasl.password

    if cacert := CONFIGURATOR.get_kafka_cacert():
        conf["ssl.ca.location"] = cacert

    return conf


def _get_consumer_config(conf_settings):  # pragma: no cover
    """Get the default consumer config"""
    conf = {
        "api.version.request": False,
        "broker.version.fallback": "0.10.2",
    }
    conf = _get_managed_kafka_config(conf)
    conf.update(conf_settings)

    return conf


def get_consumer(conf_settings):  # pragma: no cover
    """Create a Kafka consumer."""
    conf = _get_consumer_config(conf_settings)
    LOG.info(f"Consumer config {conf}")
    return Consumer(conf, logger=LOG)


def _get_producer_config(conf_settings):  # pragma: no cover
    """Return Kafka Producer config"""
    producer_conf = {}
    producer_conf = _get_managed_kafka_config(producer_conf)
    producer_conf.update(conf_settings)

    return producer_conf


def get_producer(conf_settings=None):  # pragma: no cover
    """Create a Kafka producer."""
    if conf_settings is None:
        conf_settings = {}
    conf = _get_producer_config(conf_settings)
    return ProducerSingleton(conf)


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


def check_kafka_connection():
    """Check connectability of Kafka Broker."""
    for broker in CONFIGURATOR.get_kafka_broker_list():
        host, port = broker.split(":")
        conn = BrokerConnection(host, int(port), socket.AF_UNSPEC)
        connected = conn.connect_blocking(timeout=1)
        if connected:
            conn.close()
            break
    return connected


def is_kafka_connected():
    """Wait for Kafka to become available."""
    count = 0
    result = False
    while not result:
        result = check_kafka_connection()
        if result:
            LOG.info("test connection to Kafka was successful")
        else:
            LOG.error("unable to connect to Kafka server")
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
