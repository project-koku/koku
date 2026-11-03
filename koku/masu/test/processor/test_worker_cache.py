#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Cache of worker tasks currently running."""
from unittest.mock import patch

from django.core.cache import cache
from django.core.cache.backends.db import DatabaseCache
from django.db import connection
from django.test.utils import override_settings

from masu.processor.worker_cache import rate_limit_tasks
from masu.processor.worker_cache import WorkerCache
from masu.test import MasuTestCase

# Tests run the worker cache on LocMemCache; rate_limit_tasks reads worker_cache_table,
# so the rate limit tests use the production backend.
DB_WORKER_CACHE = DatabaseCache("worker_cache_table", {})


class WorkerCacheTest(MasuTestCase):
    """Test class for the worker cache."""

    def setUp(self):
        """Set up the test."""
        super().setUp()
        cache.clear()
        # The worker cache is a process-wide LocMemCache in tests; clear it so tests do not leak state.
        WorkerCache.cache.clear()

    def tearDown(self):
        """Tear down the test."""
        super().tearDown()
        cache.clear()
        WorkerCache.cache.clear()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_worker_cache(self, mock_inspect):
        """Test the worker_cache property."""
        _worker_cache = WorkerCache().worker_cache
        self.assertEqual(_worker_cache, [])

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_invalidate_host(self, mock_inspect):
        """Test that a host's cache is invalidated."""
        task_list = [1, 2, 3]
        _cache = WorkerCache()

        for task in task_list:
            _cache.add_task_to_cache(task)
        self.assertEqual(_cache.worker_cache, task_list)

        _cache.invalidate_host()

        self.assertEqual(_cache.worker_cache, [])

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_add_task_to_cache(self, mock_inspect):
        """Test that a single task is added."""
        task_key = "task_key"
        _cache = WorkerCache()

        self.assertEqual(_cache.worker_cache, [])

        _cache.add_task_to_cache(task_key)
        self.assertEqual(_cache.worker_cache, [task_key])

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_remove_task_from_cache(self, mock_inspect):
        """Test that a task is removed."""
        task_key = "task_key"
        _cache = WorkerCache()
        _cache.add_task_to_cache(task_key)
        self.assertEqual(_cache.worker_cache, [task_key])

        _cache.remove_task_from_cache(task_key)
        self.assertEqual(_cache.worker_cache, [])

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_remove_task_from_cache_value_not_in_cache(self, mock_inspect):
        """Test that a task is removed."""
        task_list = [1, 2, 3, 4]
        _cache = WorkerCache()
        for task in task_list:
            _cache.add_task_to_cache(task)
        self.assertEqual(_cache.worker_cache, task_list)

        _cache.remove_task_from_cache(5)
        self.assertEqual(_cache.worker_cache, task_list)

    @override_settings(HOSTNAME="kokuworker")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_get_all_running_tasks(self, mock_inspect):
        """Test that multiple hosts' task lists are combined."""

        second_host = "koku-worker-2-sdfsdff"
        first_host_list = [1, 2, 3]
        second_host_list = [4, 5, 6]
        expected = first_host_list + second_host_list

        mock_worker_list = {"celery@kokuworker": "", f"celery@{second_host}": ""}
        mock_inspect.reserved.return_value = mock_worker_list

        _cache = WorkerCache()
        for task in first_host_list:
            _cache.add_task_to_cache(task)

        with override_settings(HOSTNAME=second_host):
            _cache = WorkerCache()
            for task in second_host_list:
                _cache.add_task_to_cache(task)

        self.assertEqual(sorted(_cache.get_all_running_tasks()), sorted(expected))

    @override_settings(HOSTNAME="kokuworker")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_task_is_running_true(self, mock_inspect):
        """Test that a task is running."""
        mock_worker_list = {"celery@kokuworker": ""}
        mock_inspect.reserved.return_value = mock_worker_list

        task_list = [1, 2, 3]

        _cache = WorkerCache()
        for task in task_list:
            _cache.add_task_to_cache(task)

        self.assertTrue(_cache.task_is_running(1))

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_task_is_running_false(self, mock_inspect):
        """Test that a task is not running."""
        task_list = [1, 2, 3]
        _cache = WorkerCache()
        for task in task_list:
            _cache.add_task_to_cache(task)

        self.assertFalse(_cache.task_is_running(4))

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_active_worker_property(self, mock_inspect):
        """Test the active_workers property."""
        test_matrix = [
            {"hostname": "celery@kokuworker", "expected_workers": ["kokuworker"]},
            {"hostname": "kokuworker", "expected_workers": ["kokuworker"]},
            {"hostname": "kokuworker&63)", "expected_workers": ["kokuworker&63)"]},
            {"hostname": "koku@worker&63)", "expected_workers": ["worker&63)"]},
            {"hostname": "", "expected_workers": [""]},
        ]
        for test in test_matrix:
            with self.subTest(test=test):
                mock_worker_list = {test.get("hostname"): ""}
                mock_inspect.reserved.return_value = mock_worker_list
                _cache = WorkerCache()
                self.assertEqual(_cache.active_workers, test.get("expected_workers"))

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_active_worker_property_instance_not_available(self, mock_inspect):
        """Test the active_workers property when celery inspect is not available."""
        mock_inspect.reserved.return_value = None
        _cache = WorkerCache()
        self.assertEqual(_cache.active_workers, [])

    @override_settings(HOSTNAME="kokuworker")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_remove_offline_worker_keys(self, mock_inspect):
        """Test the remove_offline_worker_keys function."""
        second_host = "kokuworker2"
        first_host_list = [1, 2, 3]
        second_host_list = [4, 5, 6]
        all_work_list = first_host_list + second_host_list

        mock_worker_list = {"celery@kokuworker": "", f"celery@{second_host}": ""}
        mock_inspect.reserved.return_value = mock_worker_list

        _cache = WorkerCache()
        for task in first_host_list:
            _cache.add_task_to_cache(task)

        with override_settings(HOSTNAME=second_host):
            _cache = WorkerCache()
            for task in second_host_list:
                _cache.add_task_to_cache(task)

        self.assertEqual(sorted(_cache.get_all_running_tasks()), sorted(all_work_list))

        # kokuworker2 goes offline
        mock_inspect.reset()
        mock_worker_list = {"celery@kokuworker": ""}
        mock_inspect.reserved.return_value = mock_worker_list
        _cache.remove_offline_worker_keys()
        self.assertEqual(sorted(_cache.get_all_running_tasks()), sorted(first_host_list))

    @override_settings(HOSTNAME="kokuworker")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_single_task_caching(self, mock_inspect):
        """Test that single task cache creates and deletes a cache entry."""
        mock_inspect.reserved.return_value = {"celery@kokuworker": []}
        cache = WorkerCache()

        task_name = "test_task"
        task_args = ["schema1", "OCP"]

        self.assertFalse(cache.single_task_is_running(task_name, task_args))
        cache.lock_single_task(task_name, task_args)
        self.assertTrue(cache.single_task_is_running(task_name, task_args))
        cache.release_single_task(task_name, task_args)
        self.assertFalse(cache.single_task_is_running(task_name, task_args))

    @override_settings(HOSTNAME="kokuworker", WORKER_CACHE_LARGE_CUSTOMER_CONCURRENT_TASKS=2)
    @patch.object(WorkerCache, "cache", DB_WORKER_CACHE)
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_rate_limit_tasks(self, mock_inspect):
        """Test that the customer is rate limited once it holds the maximum number of locks."""
        mock_inspect.reserved.return_value = {"celery@kokuworker": []}
        cache = WorkerCache()
        task_name = "test_task"
        task_args = [self.schema, "OCP", "1"]
        cache.lock_single_task(task_name, task_args)

        self.assertFalse(rate_limit_tasks(task_name, self.schema))

        task_args = [self.schema, "OCP", "2"]
        cache.lock_single_task(task_name, task_args)

        self.assertTrue(rate_limit_tasks(task_name, self.schema))

    @override_settings(WORKER_CACHE_LARGE_CUSTOMER_CONCURRENT_TASKS=2)
    def test_rate_limit_tasks_ignores_expired_locks(self):
        """Test that expired lock rows in the worker cache table do not count as running tasks."""
        task_name = "masu.processor.tasks.update_openshift_on_cloud"
        expired = [f":1:{task_name}:{self.schema}:expired-{i}" for i in range(3)]
        live = [f":1:{task_name}:{self.schema}:live-{i}" for i in range(2)]
        with connection.cursor() as cursor:
            for key in expired:
                cursor.execute(
                    "INSERT INTO public.worker_cache_table (cache_key, value, expires) "
                    "VALUES (%s, 'x', now() - interval '1 day')",
                    [key],
                )
            self.assertFalse(rate_limit_tasks(task_name, self.schema))

            cursor.execute(
                "INSERT INTO public.worker_cache_table (cache_key, value, expires) "
                "VALUES (%s, 'x', now() + interval '1 hour')",
                [live[0]],
            )
            self.assertFalse(rate_limit_tasks(task_name, self.schema))

            cursor.execute(
                "INSERT INTO public.worker_cache_table (cache_key, value, expires) "
                "VALUES (%s, 'x', now() + interval '1 hour')",
                [live[1]],
            )
            self.assertTrue(rate_limit_tasks(task_name, self.schema))


@override_settings(WORKER_CACHE_LARGE_CUSTOMER_CONCURRENT_TASKS=2)
@patch.object(WorkerCache, "cache", DB_WORKER_CACHE)
class RateLimitDeadWorkerLockTest(MasuTestCase):
    """rate_limit_tasks counts only locks held by live workers."""

    task_name = "masu.processor.tasks.update_summary_tables"

    def lock_as(self, host, *task_args, task_name=None, schema=None):
        """Take a lock the way a worker named host does."""
        with override_settings(HOSTNAME=host), patch("masu.processor.worker_cache.CELERY_INSPECT") as inspect:
            inspect.reserved.return_value = {f"celery@{host}": []}
            WorkerCache().lock_single_task(
                task_name or self.task_name, [schema or self.schema, *task_args], timeout=3600
            )

    def set_live_workers(self, *hosts):
        """Set the live worker set, as WorkerCache() leaves it after pruning offline workers."""
        DB_WORKER_CACHE.set("keys", set(hosts))

    def test_live_locks_rate_limit(self):
        """Two locks held by live workers rate limit the customer."""
        self.lock_as("worker-a", "1")
        self.lock_as("worker-b", "2")
        self.set_live_workers("worker-a", "worker-b")
        self.assertTrue(rate_limit_tasks(self.task_name, self.schema))

    def test_lock_of_dead_worker_does_not_count(self):
        """A lock whose worker is gone does not count toward the limit."""
        self.lock_as("worker-a", "1")
        self.lock_as("worker-dead", "2")
        self.set_live_workers("worker-a")
        self.assertFalse(rate_limit_tasks(self.task_name, self.schema))

    def test_locks_of_dead_workers_only(self):
        """Locks held only by dead workers never rate limit."""
        self.lock_as("worker-dead-1", "1")
        self.lock_as("worker-dead-2", "2")
        self.set_live_workers("worker-a")
        self.assertFalse(rate_limit_tasks(self.task_name, self.schema))

    def test_expired_locks_of_live_workers_do_not_count(self):
        """Expired locks stay ignored when the live worker set is known."""
        self.lock_as("worker-a", "1")
        self.lock_as("worker-a", "2")
        self.set_live_workers("worker-a")
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE public.worker_cache_table SET expires = now() - interval '1 minute' WHERE cache_key LIKE %s",
                [f"%{self.task_name}%"],
            )
        self.assertFalse(rate_limit_tasks(self.task_name, self.schema))

    def test_other_schema_and_task_locks_do_not_count(self):
        """Locks for another schema or another task do not count."""
        self.lock_as("worker-a", "1")
        self.lock_as("worker-a", "2", schema="org7654321")
        self.lock_as("worker-a", "3", task_name="masu.processor.tasks.update_cost_model_costs")
        self.set_live_workers("worker-a")
        self.assertFalse(rate_limit_tasks(self.task_name, self.schema))

    def test_unknown_live_workers_counts_every_lock(self):
        """Without a live worker set every unexpired lock counts, as before."""
        self.lock_as("worker-dead-1", "1")
        self.lock_as("worker-dead-2", "2")
        DB_WORKER_CACHE.delete("keys")
        self.assertTrue(rate_limit_tasks(self.task_name, self.schema))

    def test_lock_with_unresolvable_key_counts(self):
        """A lock row that is not a default-version cache key counts, as before."""
        self.lock_as("worker-a", "1")
        self.set_live_workers("worker-a")
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO public.worker_cache_table (cache_key, value, expires) "
                "VALUES (%s, 'x', now() + interval '1 hour')",
                [f":2:{self.task_name}:{self.schema}:2"],
            )
        self.assertTrue(rate_limit_tasks(self.task_name, self.schema))
