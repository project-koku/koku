#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for koku.advisory_locks."""
from unittest.mock import patch
from uuid import uuid4

import django.test
import psycopg2
from django.db import connection
from django.db import OperationalError
from django.db import transaction

from koku.advisory_locks import AdvisoryLockTimeout
from koku.advisory_locks import lock_providers_for_transaction
from koku.advisory_locks import provider_session_lock


class AdvisoryLocksTest(django.test.TransactionTestCase):
    """Session-level and transaction-level provider locks share keys and release cleanly."""

    def _fixture_teardown(self):
        """Nothing to flush; these tests write no rows (and django-tenants breaks the flush)."""

    def setUp(self):
        params = connection.settings_dict
        self.other = psycopg2.connect(
            dbname=params["NAME"],
            user=params["USER"],
            password=params["PASSWORD"],
            host=params["HOST"],
            port=params["PORT"],
        )
        self.other.autocommit = True

    def tearDown(self):
        self.other.close()

    def _other_can_lock(self, provider_uuid):
        with self.other.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s))", [str(provider_uuid)])
            acquired = cursor.fetchone()[0]
            if acquired:
                cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [str(provider_uuid)])
        return acquired

    def _lock_timeout(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('lock_timeout')")
            return cursor.fetchone()[0]

    def test_requires_atomic_block(self):
        """Outside a transaction the locks would be released by the very statement that took them."""
        with self.assertRaises(RuntimeError):
            lock_providers_for_transaction([uuid4()], 100)

    def test_transaction_lock_conflicts_with_session_lock(self):
        """A transaction-level lock waits for a session-level lock on the same provider, then times out."""
        provider_uuid = uuid4()
        with provider_session_lock(provider_uuid):
            self.assertFalse(self._other_can_lock(provider_uuid))
            with self.other.cursor() as cursor:
                cursor.execute("BEGIN")
                cursor.execute("SET LOCAL lock_timeout = '100ms'")
                with self.assertRaises(psycopg2.errors.LockNotAvailable):
                    cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [str(provider_uuid)])
                cursor.execute("ROLLBACK")
        self.assertTrue(self._other_can_lock(provider_uuid))

    def test_restores_lock_timeout_and_releases_at_commit(self):
        """The time budget applies only to taking the locks; the caller's lock_timeout comes back afterwards."""
        provider_uuids = [uuid4(), uuid4()]
        with transaction.atomic():
            previous = self._lock_timeout()
            lock_providers_for_transaction(provider_uuids + provider_uuids, 1000)
            self.assertEqual(self._lock_timeout(), previous)
            for provider_uuid in provider_uuids:
                self.assertFalse(self._other_can_lock(provider_uuid))
        for provider_uuid in provider_uuids:
            self.assertTrue(self._other_can_lock(provider_uuid))

    def test_timeout_raises_advisory_lock_timeout(self):
        """Running out of budget raises AdvisoryLockTimeout, not a bare OperationalError."""
        provider_uuid = uuid4()
        with self.other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(hashtext(%s))", [str(provider_uuid)])
        with self.assertRaises(AdvisoryLockTimeout), transaction.atomic():
            lock_providers_for_transaction([provider_uuid], 100)

    def test_other_database_errors_propagate(self):
        """Only lock_not_available becomes AdvisoryLockTimeout; any other database error is re-raised as is."""
        error = OperationalError("connection lost")
        with (
            patch("koku.advisory_locks.connection.cursor") as cursor,
            patch("koku.advisory_locks.connection.in_atomic_block", True),
        ):
            cursor.return_value.__enter__.return_value.execute.side_effect = [None, None, error]
            cursor.return_value.__enter__.return_value.fetchone.return_value = ["0"]
            with self.assertRaises(OperationalError) as ctx:
                lock_providers_for_transaction([uuid4()], 100)
        self.assertIs(ctx.exception, error)
