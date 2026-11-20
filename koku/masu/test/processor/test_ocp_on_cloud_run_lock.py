#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the source-pair month OCP-on-cloud run lock."""
import uuid
from datetime import date

from django.db import connections
from django.test import TestCase

from masu.processor.ocp_on_cloud_run_lock import LOCK_NAMESPACE
from masu.processor.ocp_on_cloud_run_lock import ocp_on_cloud_month_locks

JUNE = date(2026, 6, 1)
JULY = date(2026, 7, 1)


class OcpOnCloudMonthLocksTest(TestCase):
    """ocp_on_cloud_month_locks against a second database session."""

    def setUp(self):
        self.openshift_provider_uuid = str(uuid.uuid4())
        self.infrastructure_provider_uuid = str(uuid.uuid4())
        self.other = connections.create_connection("default")
        self.addCleanup(self.other.close)

    def _key(self, month, infrastructure_provider_uuid=None):
        infrastructure_provider_uuid = infrastructure_provider_uuid or self.infrastructure_provider_uuid
        return f"{self.openshift_provider_uuid}:{infrastructure_provider_uuid}:{month.isoformat()}"

    def _other_try(self, month, infrastructure_provider_uuid=None):
        """Try the lock from the other session; release it again when taken."""
        key = self._key(month, infrastructure_provider_uuid)
        with self.other.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s), hashtext(%s))", [LOCK_NAMESPACE, key])
            taken = cursor.fetchone()[0]
            if taken:
                cursor.execute("SELECT pg_advisory_unlock(hashtext(%s), hashtext(%s))", [LOCK_NAMESPACE, key])
        return taken

    def _other_hold(self, month, infrastructure_provider_uuid=None):
        key = self._key(month, infrastructure_provider_uuid)
        with self.other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(hashtext(%s), hashtext(%s))", [LOCK_NAMESPACE, key])

    def test_holds_the_lock_and_releases_it(self):
        """Another session cannot take a held month; it can once the context exits."""
        with ocp_on_cloud_month_locks(
            self.openshift_provider_uuid, self.infrastructure_provider_uuid, [JUNE], wait_seconds=0
        ) as acquired:
            self.assertTrue(acquired)
            self.assertFalse(self._other_try(JUNE))
            self.assertTrue(self._other_try(JULY), "a different month of the source pair is not locked")
        self.assertTrue(self._other_try(JUNE))

    def test_a_different_source_pair_is_not_locked(self):
        """The same OpenShift source against another cloud source runs in parallel."""
        with ocp_on_cloud_month_locks(
            self.openshift_provider_uuid, self.infrastructure_provider_uuid, [JUNE], wait_seconds=0
        ) as acquired:
            self.assertTrue(acquired)
            self.assertTrue(self._other_try(JUNE, infrastructure_provider_uuid=str(uuid.uuid4())))

    def test_busy_month_yields_false_after_the_wait(self):
        """A month held elsewhere stays busy: the context yields False once the wait runs out."""
        self._other_hold(JUNE)
        with ocp_on_cloud_month_locks(
            self.openshift_provider_uuid,
            self.infrastructure_provider_uuid,
            [JUNE],
            wait_seconds=0.2,
            poll_seconds=0.05,
        ) as acquired:
            self.assertFalse(acquired)

    def test_busy_month_releases_the_months_taken_before_it(self):
        """When a later month is busy, the earlier months taken are released again."""
        self._other_hold(JULY)
        with ocp_on_cloud_month_locks(
            self.openshift_provider_uuid,
            self.infrastructure_provider_uuid,
            [JULY, JUNE],
            wait_seconds=0.2,
            poll_seconds=0.05,
        ) as acquired:
            self.assertFalse(acquired)
            self.assertTrue(self._other_try(JUNE), "June must not stay locked while the run gives up")

    def test_releases_the_lock_when_the_body_raises(self):
        """An error inside the context still releases the locks."""
        with self.assertRaises(RuntimeError):
            with ocp_on_cloud_month_locks(
                self.openshift_provider_uuid, self.infrastructure_provider_uuid, [JUNE], wait_seconds=0
            ):
                raise RuntimeError("writer failed")
        self.assertTrue(self._other_try(JUNE))
