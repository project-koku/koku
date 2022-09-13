#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Configuration for Source Service."""
from koku.configurator import CONFIGURATOR
from koku.env import ENVIRONMENT


class Config:
    """Configuration for service."""

    # SOURCES_TOPIC = ENVIRONMENT.get_value("SOURCES_KAFKA_TOPIC", default="platform.sources.event-stream")
    SOURCES_TOPIC = CONFIGURATOR.get_kafka_topic("platform.sources.event-stream")

    SOURCES_KAFKA_HOST = CONFIGURATOR.get_kafka_broker_host()
    SOURCES_KAFKA_PORT = CONFIGURATOR.get_kafka_broker_port()
    SOURCES_KAFKA_ADDRESS = f"{SOURCES_KAFKA_HOST}:{SOURCES_KAFKA_PORT}"
    SOURCES_KAFKA_SASL = CONFIGURATOR.get_kafka_sasl()
    SOURCES_KAFKA_CACERT = CONFIGURATOR.get_kafka_cacert()
    SOURCES_KAFKA_AUTHTYPE = CONFIGURATOR.get_kafka_authtype()

    SOURCES_API_HOST = CONFIGURATOR.get_endpoint_host("sources-api", "svc", "localhost")
    SOURCES_API_PORT = CONFIGURATOR.get_endpoint_port("sources-api", "svc", "3000")
    SOURCES_API_URL = f"http://{SOURCES_API_HOST}:{SOURCES_API_PORT}"
    SOURCES_API_PREFIX = ENVIRONMENT.get_value("SOURCES_API_PREFIX", default="/api/v1.0")
    SOURCES_INTERNAL_API_PREFIX = ENVIRONMENT.get_value("SOURCES_INTERNAL_API_PREFIX", default="/internal/v1.0")
    SOURCES_PROBE_HEADER = ENVIRONMENT.get_value(
        "SOURCES_PROBE_HEADER",
        default="eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1iZXIiOiAiMTIzNDUiLCAib3JnX2lkIjogIjEyMzQ1In19Cg==",
    )
    SOURCES_FAKE_HEADER = ENVIRONMENT.get_value(
        "SOURCES_FAKE_HEADER",
        default=(
            "eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1iZXIiOiAiMTIzNDUiLCAib3JnX2lkIjogIjMzMzM"
            "zMzMiLCAidXNlciI6IHsiaXNfb3JnX2FkbWluIjogImZhbHNlIiwgInVzZXJuYW1lIjogInNvdX"
            "JjZXMiLCAiZW1haWwiOiAic291cmNlc0Bzb3VyY2VzLmlvIn0sICJpbnRlcm5hbCI6IHsib3JnX"
            "2lkIjogIjMzMzMzMzMifX19"
        ),
    )
    SOURCES_FAKE_CLUSTER_HEADER = ENVIRONMENT.get_value(
        "SOURCES_FAKE_CLUSTER_HEADER",
        default=(
            "eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1iZXIiOiAiMTIzNDUiLCAib3JnX2lkIjogIjMzMzMzMzM"
            "iLCAiYXV0aF90eXBlIjogInVoYy1hdXRoIiwgInR5cGUiOiAiU3lzdGVtIiwgInN5c3RlbSI6IHsiY2"
            "x1c3Rlcl9pZCI6ICIwYmIyOTEzNS1kNmQxLTQ3OGItYjViNi02YmQxMjljYjZkNWQifSwgImludGVyb"
            "mFsIjogeyJvcmdfaWQiOiAiMzMzMzMzMyJ9fX0="
        ),
    )
    SOURCES_PSK = ENVIRONMENT.get_value("SOURCES_PSK", default="sources-psk")

    RETRY_SECONDS = ENVIRONMENT.int("RETRY_SECONDS", default=10)
