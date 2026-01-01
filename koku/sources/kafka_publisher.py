#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Kafka event publisher for Sources events."""
import json
import logging
from typing import List
from typing import Tuple

from api.provider.models import Sources
from kafka_utils.utils import delivery_callback
from kafka_utils.utils import get_producer
from kafka_utils.utils import SOURCES_TOPIC

LOG = logging.getLogger(__name__)


def _build_kafka_headers(source: Sources, event_type: str) -> List[Tuple[str, bytes]]:
    """Build Kafka message headers.

    Args:
        source: Sources model instance
        event_type: Event type string

    Returns:
        List of tuples containing (header_key, header_value) pairs
    """
    headers = [
        ("event_type", event_type.encode("utf-8")),
        ("encoding", b"json"),
    ]

    # Add identity headers if available
    if source.account_id:
        headers.append(("x-rh-sources-account-number", source.account_id.encode("utf-8")))

    if source.org_id:
        headers.append(("x-rh-sources-org-id", source.org_id.encode("utf-8")))

    # Add x-rh-identity from auth_header if available
    if source.auth_header:
        headers.append(("x-rh-identity", source.auth_header.encode("utf-8")))

    return headers


def _get_message_key_from_headers(headers: List[Tuple[str, bytes]], source_id: int) -> str:
    """Extract message key from headers using sources-api-go precedence.

    sources-api-go uses this precedence (from kafka/message.go SetKeyFromHeaders):
    1. x-rh-sources-org-id (OrgID)
    2. x-rh-sources-account-number (AccountNumber)
    3. x-rh-identity (XRHID)

    Args:
        headers: List of Kafka message headers
        source_id: Source ID to use as final fallback

    Returns:
        Message key string
    """
    # Precedence 1: x-rh-sources-org-id
    for header_key, header_value in headers:
        if header_key == "x-rh-sources-org-id":
            return header_value.decode("utf-8")

    # Precedence 2: x-rh-sources-account-number
    for header_key, header_value in headers:
        if header_key == "x-rh-sources-account-number":
            return header_value.decode("utf-8")

    # Precedence 3: x-rh-identity
    for header_key, header_value in headers:
        if header_key == "x-rh-identity":
            return header_value.decode("utf-8")

    # Fallback to source_id if no headers available (not in sources-api-go, but safe fallback)
    return str(source_id)


def publish_application_destroy_event(source: Sources, application_type_id=None) -> None:
    """Publish destroy event to Kafka for ros-ocp-backend compatibility.

    Args:
        source: Sources model instance
        application_type_id: Cost management application type ID (optional)
    """
    try:
        event_type = "Application.destroy"
        payload = {
            "Id": source.source_id,  # Application ID (ros-ocp-backend doesn't use this, but it's required)
            "Source_id": source.source_id,  # This is what ros-ocp-backend actually uses to find clusters
            "Application_type_id": None,  # TODO: REMOVE
            "Tenant": source.org_id or source.account_id,  # Required, prefer org_id
        }
        headers = _build_kafka_headers(source, event_type)
        message_key = _get_message_key_from_headers(headers, source.source_id)

        # Serialize the event payload
        message_value = json.dumps(payload).encode("utf-8")

        # Get Kafka producer
        producer = get_producer()

        # Publish the event
        producer.produce(
            SOURCES_TOPIC,
            key=message_key,
            value=message_value,
            headers=headers,
            callback=delivery_callback,
        )
        producer.poll(0)

        LOG.info(f"[publish_application_destroy_event] Published {event_type} event for source_id: {source.source_id}")
    except Exception as error:
        # Log error but don't fail - deletion already succeeded
        LOG.error(
            f"[publish_application_destroy_event] Failed to publish event for source_id: {source.source_id}."
            f"Error: {error}"
        )
