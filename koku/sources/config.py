#
# Copyright 2019 Red Hat, Inc.
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

    SOURCES_API_HOST = ENVIRONMENT.get_value("SOURCES_API_HOST", default="localhost")
    SOURCES_API_PORT = ENVIRONMENT.get_value("SOURCES_API_PORT", default="3000")
    SOURCES_API_URL = f"http://{SOURCES_API_HOST}:{SOURCES_API_PORT}"
    SOURCES_API_PREFIX = ENVIRONMENT.get_value("SOURCES_API_PREFIX", default="/api/v1.0")
    SOURCES_INTERNAL_API_PREFIX = ENVIRONMENT.get_value("SOURCES_INTERNAL_API_PREFIX", default="/internal/v1.0")
    SOURCES_FAKE_HEADER = ENVIRONMENT.get_value(
        "SOURCES_FAKE_HEADER",
        default=(
            "eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1iZXIiOiAiMTIzNDUiLCAidXNlciI6IHsiaXNfb3J"
            "nX2FkbWluIjogImZhbHNlIiwgInVzZXJuYW1lIjogInNvdXJjZXMiLCAiZW1haWwiOiAic291cm"
            "Nlc0Bzb3VyY2VzLmlvIn0sICJpbnRlcm5hbCI6IHsib3JnX2lkIjogIjU0MzIxIn19fQ=="
        ),
    )
    SOURCES_FAKE_CLUSTER_HEADER = ENVIRONMENT.get_value(
        "SOURCES_FAKE_CLUSTER_HEADER",
        default=(
            "eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1iZXIiOiAiMTIzNDUiLCAiYXV0aF90eXBlIjogInVoYy1"
            "hdXRoIiwgInR5cGUiOiAiU3lzdGVtIiwgInN5c3RlbSI6IHsiY2x1c3Rlcl9pZCI6ICIwYmIyOTEzNS1k"
            "NmQxLTQ3OGItYjViNi02YmQxMjljYjZkNWQifSwgImludGVybmFsIjogeyJvcmdfaWQiOiAiNTQzMjEifX19"
        ),
    )
    KOKU_API_HOST = ENVIRONMENT.get_value("KOKU_API_HOST", default="localhost")
    KOKU_API_PORT = ENVIRONMENT.get_value("KOKU_API_PORT", default="8000")
    KOKU_API_PATH_PREFIX = ENVIRONMENT.get_value("KOKU_API_PATH_PREFIX", default="/api/cost-management")
    KOKU_API_URL = f"http://{KOKU_API_HOST}:{KOKU_API_PORT}{KOKU_API_PATH_PREFIX}/v1"

    RETRY_SECONDS = ENVIRONMENT.int("RETRY_SECONDS", default=10)
