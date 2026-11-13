#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Run cost model updates for one provider and month one at a time (COST-8575).

Every cost model writer deletes its window and then inserts, as separate statements.
update_cost_model_costs runs for the same provider with different, overlapping windows
can run at the same time (WorkerCache keys on the dates), and when one run's insert
lands after the other run's delete, both runs' rows survive. Holding a lock per
provider and billing month for the whole run keeps such runs apart while different
months of a provider still run in parallel.
"""
import logging
import time
from contextlib import contextmanager

from django.db import connection

from api.utils import DateHelper

LOG = logging.getLogger(__name__)

# Two-integer advisory lock keys: hashtext(LOCK_NAMESPACE) and hashtext("<provider>:<month>").
# PostgreSQL keeps the two-integer key space apart from single-key advisory locks (the
# distribution lock in OCPReportDBAccessor), so the two never collide.
LOCK_NAMESPACE = "cost_model_run"
# How long a run waits for a busy lock before it hands its window to the delayed tasks.
LOCK_WAIT_SECONDS = 120
LOCK_POLL_SECONDS = 2


def billing_months(start_date, end_date):
    """Return the first day of every billing month in [start_date, end_date], in order."""
    return [month_start.replace(day=1) for month_start, _ in DateHelper().list_month_tuples(start_date, end_date)]


def cost_model_run_months(start_date, end_date):
    """Billing months a cost model run for [start_date, end_date] writes, in order.

    Its own months, plus the previous month on the 2nd when the range covers the current month:
    the full-month GPU distribution of such a run covers the whole previous month
    (OCPReportDBAccessor.populate_distributed_cost_sql, requires_full_month; COST-8586), so the run
    must hold that month's lock too.
    """
    months = billing_months(start_date, end_date)
    dh = DateHelper()
    previous = dh.last_month_start.date()
    if dh.now_utc.day == 2 and dh.this_month_start.date() in months and previous not in months:
        months.insert(0, previous)
    return months


def _lock_key(provider_uuid, month):
    return f"{provider_uuid}:{month.isoformat()}"


def _try_lock(key):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s), hashtext(%s))", [LOCK_NAMESPACE, key])
        return cursor.fetchone()[0]


def _unlock(key):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(hashtext(%s), hashtext(%s))", [LOCK_NAMESPACE, key])


@contextmanager
def provider_month_locks(provider_uuid, months, wait_seconds=LOCK_WAIT_SECONDS, poll_seconds=LOCK_POLL_SECONDS):
    """Hold the cost model run lock of every month for one provider; yield whether all were acquired.

    Locks are taken in month order, so runs that span several months cannot deadlock.
    The wait for all of them together is bounded by ``wait_seconds``. When a lock is
    still busy at the deadline, the locks taken so far are released and the context
    yields False: the caller must not write, and should hand the window on.

    The locks are session-level on Django's connection, outside any transaction, so
    the autocommitted statements of the writers (and their retry on deadlock) work
    unchanged. If the worker dies, PostgreSQL releases the locks with its session.
    """
    deadline = time.monotonic() + wait_seconds
    held = []
    acquired = True
    try:
        for month in sorted(set(months)):
            key = _lock_key(provider_uuid, month)
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
