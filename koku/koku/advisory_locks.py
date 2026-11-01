#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Per-provider PostgreSQL advisory locks that serialize writes to rates_to_usage.

Every holder uses the key pg_advisory_*lock(hashtext(str(provider_uuid))).
Session-level and transaction-level advisory locks on the same key conflict
across sessions, so the two modes below serialize against each other.

- provider_session_lock: for masu RTU writers, whose statements autocommit one
  at a time (see OCPReportDBAccessor._distribution_provider_lock for why).
- lock_providers_for_transaction: for API code that changes data inside a
  transaction. The locks are released by PostgreSQL when the outermost
  transaction commits or rolls back, so no unlock statement can fail on an
  aborted transaction and leak a lock.
"""
import time
from contextlib import contextmanager

from django.db import connection
from django.db import OperationalError

LOCK_NOT_AVAILABLE = "55P03"


class AdvisoryLockTimeout(Exception):
    """Raised when a provider lock could not be acquired within the time budget."""


@contextmanager
def provider_session_lock(provider_uuid):
    """Hold a provider's session-level advisory lock for the duration of the block."""
    lock_key = str(provider_uuid)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(hashtext(%s))", [lock_key])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [lock_key])


def lock_providers_for_transaction(provider_uuids, timeout_ms):
    """Take transaction-level advisory locks for the given providers, waiting at most timeout_ms in total.

    Must run inside transaction.atomic(). Locks are taken in sorted order so two
    callers locking overlapping sets cannot deadlock each other. On timeout the
    caller's atomic block rolls back, which also releases any locks taken here
    and restores lock_timeout.

    Raises AdvisoryLockTimeout if the budget runs out.
    """
    if not connection.in_atomic_block:
        raise RuntimeError("lock_providers_for_transaction must run inside transaction.atomic()")
    lock_keys = sorted({str(provider_uuid) for provider_uuid in provider_uuids})
    if not lock_keys:
        return
    deadline = time.monotonic() + timeout_ms / 1000
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('lock_timeout')")
        previous_lock_timeout = cursor.fetchone()[0]
        for lock_key in lock_keys:
            # lock_timeout = 0 means "wait forever", so never let the remaining budget round down to 0.
            remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
            cursor.execute("SELECT set_config('lock_timeout', %s, true)", [f"{remaining_ms}ms"])
            try:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [lock_key])
            except OperationalError as error:
                if getattr(error.__cause__, "pgcode", None) == LOCK_NOT_AVAILABLE:
                    raise AdvisoryLockTimeout(
                        f"timed out after {timeout_ms} ms waiting for the advisory lock of provider {lock_key}"
                    ) from error
                raise
        cursor.execute("SELECT set_config('lock_timeout', %s, true)", [previous_lock_timeout])
