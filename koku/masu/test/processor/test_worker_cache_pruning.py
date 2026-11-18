#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test dropping offline workers from the worker cache."""
from unittest.mock import patch

from django.conf import settings
from django.test.utils import override_settings

from masu.processor.worker_cache import WORKER_OFFLINE_GRACE_SECONDS
from masu.processor.worker_cache import WorkerCache
from masu.test import MasuTestCase

GRACE = WORKER_OFFLINE_GRACE_SECONDS
T0 = 1_700_000_000.0
TASK = "masu.processor.tasks.update_summary_tables"
TASK_ARGS = ["org1234567", "OCP", "uuid", "2026-11"]


class WorkerPruningTest(MasuTestCase):
    """Workers that miss Celery inspect replies are dropped only after a grace period."""

    def setUp(self):
        """Mock Celery inspect and the clock; start with an empty worker cache."""
        super().setUp()
        WorkerCache.cache.clear()
        self.addCleanup(WorkerCache.cache.clear)
        inspect_patcher = patch("masu.processor.worker_cache.CELERY_INSPECT")
        self.inspect = inspect_patcher.start()
        self.addCleanup(inspect_patcher.stop)
        clock_patcher = patch("masu.processor.worker_cache._now", return_value=T0)
        self.clock = clock_patcher.start()
        self.addCleanup(clock_patcher.stop)

    def at(self, seconds_after_t0, *replying_hosts, as_host="worker-a"):
        """Build a WorkerCache as as_host at T0 + seconds while only replying_hosts answer inspect."""
        self.clock.return_value = T0 + seconds_after_t0
        self.inspect.reserved.return_value = {f"celery@{host}": [] for host in replying_hosts} or None
        with override_settings(HOSTNAME=as_host):
            return WorkerCache()

    def start_two_workers(self):
        """worker-a runs task 1; worker-b runs task 2 and holds a single-task lock."""
        self.at(0, "worker-a", "worker-b").add_task_to_cache(1)
        worker_b = self.at(0, "worker-a", "worker-b", as_host="worker-b")
        worker_b.add_task_to_cache(2)
        with override_settings(HOSTNAME="worker-b"):
            worker_b.lock_single_task(TASK, TASK_ARGS, timeout=3600)

    def assert_worker_b_kept(self, cache):
        self.assertIn("worker-b", cache.worker_cache_keys)
        self.assertEqual(sorted(cache.get_all_running_tasks()), [1, 2])
        self.assertTrue(cache.single_task_is_running(TASK, TASK_ARGS))

    def assert_worker_b_dropped(self, cache):
        self.assertNotIn("worker-b", cache.worker_cache_keys)
        self.assertEqual(sorted(cache.get_all_running_tasks()), [1])
        self.assertFalse(cache.single_task_is_running(TASK, TASK_ARGS))
        # Its task list is deleted too, so a worker coming back under the same name starts empty.
        self.assertIsNone(WorkerCache.cache.get(settings.WORKER_CACHE_KEY, version="worker-b"))

    def test_no_replies_drops_nothing(self):
        """Without any inspect reply liveness is unknown, so no worker is dropped."""
        self.start_two_workers()
        cache = self.at(10 * GRACE)
        self.assertIn("worker-a", cache.worker_cache_keys)
        self.assert_worker_b_kept(cache)

    def test_missing_worker_kept_within_grace(self):
        """A worker missing from one inspect reply keeps its tasks and locks."""
        self.start_two_workers()
        self.assert_worker_b_kept(self.at(60, "worker-a"))

    def test_missing_worker_dropped_after_grace(self):
        """A worker unseen for longer than the grace period is dropped with its tasks."""
        self.start_two_workers()
        self.at(60, "worker-a")
        self.assert_worker_b_dropped(self.at(GRACE + 1, "worker-a"))

    def test_worker_kept_at_exactly_grace(self):
        """A worker unseen for exactly the grace period is still kept."""
        self.start_two_workers()
        self.assert_worker_b_kept(self.at(GRACE, "worker-a"))

    def test_reappearing_worker_resets_grace(self):
        """A worker seen again starts a new grace period."""
        self.start_two_workers()
        self.at(60, "worker-a")
        self.at(GRACE - 10, "worker-a", "worker-b")
        self.assert_worker_b_kept(self.at(GRACE + 60, "worker-a"))

    def test_calling_worker_counts_as_seen(self):
        """The worker building the cache is alive even if its own inspect reply was late."""
        self.start_two_workers()
        cache = self.at(GRACE + 1, "worker-b")
        self.assertIn("worker-a", cache.worker_cache_keys)
        self.assertEqual(sorted(cache.get_all_running_tasks()), [1, 2])

    def test_worker_without_last_seen_gets_grace(self):
        """A worker key without a last-seen time (written before this change) gets a grace period."""
        WorkerCache.cache.set("keys", {"worker-a", "worker-old"})
        WorkerCache.cache.set("worker", [7], version="worker-old")
        cache = self.at(0, "worker-a")
        self.assertIn("worker-old", cache.worker_cache_keys)
        self.assertEqual(cache.get_all_running_tasks(), [7])
        cache = self.at(GRACE + 1, "worker-a")
        self.assertNotIn("worker-old", cache.worker_cache_keys)
        self.assertEqual(cache.get_all_running_tasks(), [])

    def test_last_seen_entries_expire(self):
        """Last-seen times are kept for seen workers and dropped once older than the grace period."""
        self.at(0, "worker-a", "worker-ghost")
        last_seen = WorkerCache.cache.get("keys_last_seen")
        self.assertEqual(last_seen, {"worker-a": T0, "worker-ghost": T0})
        self.at(GRACE + 1, "worker-a")
        last_seen = WorkerCache.cache.get("keys_last_seen")
        self.assertEqual(last_seen, {"worker-a": T0 + GRACE + 1})
