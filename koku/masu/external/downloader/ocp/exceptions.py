#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Listener-facing errors and confirmation statuses for HCCM ingress."""


class KafkaMsgHandlerError(Exception):
    """Raised so the Kafka consumer rewinds and retries the message."""


SUCCESS_CONFIRM_STATUS = "success"
FAILURE_CONFIRM_STATUS = "failure"
