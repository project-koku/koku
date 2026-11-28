#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Run OCP-on-cloud summaries for one source pair and month one at a time (COST-8410).

update_openshift_on_cloud rewrites OCP-on-cloud summary data with delete and insert
statements, and for large tenants one run can outlive the WorkerCache lock that was
supposed to keep duplicate runs of the same work apart: the lock expired mid-run,
two workers raced past its check-and-set, or a stale owner cleared a successor's
lock, so identical runs overlapped and requeued copies amplified the queue. Holding
an advisory lock per (OpenShift source, cloud source, billing month) for the whole
run keeps such runs apart while different months and different source pairs still
run in parallel.
"""
import logging
import time
from contextlib import contextmanager

from django.db import connection

LOG = logging.getLogger(__name__)

# Two-integer advisory lock keys: hashtext(LOCK_NAMESPACE) and hashtext("<ocp>:<infra>:<month>").
# PostgreSQL keeps the two-integer key space apart from single-key advisory locks (the
# distribution lock in OCPReportDBAccessor), and the namespace keeps this lock apart from
# the cost model run lock (cost_model_run_lock.LOCK_NAMESPACE), so the two never collide.
LOCK_NAMESPACE = "ocp_on_cloud_run"
# How long a run waits for a busy lock before it hands its window to the delayed tasks.
LOCK_WAIT_SECONDS = 120
LOCK_POLL_SECONDS = 2


def _lock_key(openshift_provider_uuid, infrastructure_provider_uuid, month):
    return f"{openshift_provider_uuid}:{infrastructure_provider_uuid}:{month.isoformat()}"


def _try_lock(key):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s), hashtext(%s))", [LOCK_NAMESPACE, key])
        return cursor.fetchone()[0]


def _unlock(key):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(hashtext(%s), hashtext(%s))", [LOCK_NAMESPACE, key])


@contextmanager
def ocp_on_cloud_month_locks(
    openshift_provider_uuid,
    infrastructure_provider_uuid,
    months,
    wait_seconds=LOCK_WAIT_SECONDS,
    poll_seconds=LOCK_POLL_SECONDS,
):
    """Hold the run lock of every month for one source pair; yield whether all were acquired.

    Locks are taken in month order, so runs that span several months cannot deadlock.
    The wait for all of them together is bounded by ``wait_seconds``. When a lock is
    still busy at the deadline, the locks taken so far are released and the context
    yields False: the caller must not write, and should hand the window on.

    The locks are session-level on Django's connection, outside any transaction, so
    the autocommitted statements of the summary writers work unchanged. They cannot
    expire mid-run, and if the worker dies PostgreSQL releases them with its session.
    """
    deadline = time.monotonic() + wait_seconds
    held = []
    acquired = True
    try:
        for month in sorted(set(months)):
            key = _lock_key(openshift_provider_uuid, infrastructure_provider_uuid, month)
            while not _try_lock(key):
                if time.monotonic() >= deadline:
                    acquired = False
                    break
                time.sleep(poll_seconds)
            if not acquired:
                break
            held.append(key)
        if not acquired:
            for key in reversed(held):
                _unlock(key)
            held = []
        yield acquired
    finally:
        for key in reversed(held):
            _unlock(key)
