#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Timing, batch sizes, and Celery task names for ingress staging."""
from datetime import timedelta

from django.db import InterfaceError
from django.db import OperationalError
from django.db import ProgrammingError

# Long enough that a healthy line-item run is not reclaimed, short enough that
# a dead worker is retried. Matches the rough upper bound used for large downloads.
INGRESS_STAGING_LEASE = timedelta(hours=2)
# After extract enqueues line items, ``enqueued_at`` blocks reclaim until this
# window ends so a backed-up OCP queue does not look like a dead worker.
INGRESS_STAGING_HANDOFF_LEASE = timedelta(hours=24)
INGRESS_STAGING_BEAT_GRACE = timedelta(minutes=1)
INGRESS_STAGING_RETENTION = timedelta(days=7)
INGRESS_STAGING_RECONCILE_BATCH = 100
# Hourly expire task loops in batches of 100 until the backlog is gone or this
# budget elapses so retention does not fall behind a burst of processed rows.
INGRESS_STAGING_EXPIRE_TIME_BUDGET = timedelta(minutes=55)
# One beat registers this many markers so a long outage drains faster than the
# row reconciler's batch of 100, without listing the prefix without a cap.
INGRESS_STAGING_REGISTER_LIMIT = 1000
_LAST_ERROR_MAX_LENGTH = 1024
_DB_ERRORS = (OperationalError, InterfaceError, ProgrammingError)
_MISSING_S3_CODES = {"404", "NoSuchKey", "NotFound"}

PROCESS_STAGED_INGRESS_TASK = "masu.processor.ocp.staged_payloads.process_staged.process_staged_ingress_payload"
REGISTER_INGRESS_STAGING_TASK = "masu.external.downloader.ocp.payload_landing.register_ingress_staging_marker"
RECONCILE_INGRESS_STAGING_TASK = "masu.external.downloader.ocp.payload_landing.reconcile_ingress_staging"
EXPIRE_INGRESS_STAGING_TASK = "masu.external.downloader.ocp.payload_landing.expire_ingress_staging"
