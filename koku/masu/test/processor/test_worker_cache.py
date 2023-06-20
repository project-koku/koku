#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Cache of worker tasks currently running."""
from unittest.mock import patch

from django.core.cache import cache
from django.test.utils import override_settings

from masu.processor.worker_cache import rate_limit_tasks
from masu.processor.worker_cache import WorkerCache
from masu.test import MasuTestCase


class WorkerCacheTest(MasuTestCase):
    """Test class for the worker cache."""

    def setUp(self):
        """Set up the test."""
        super().setUp()
        cache.clear()

    def tearDown(self):
        """Tear down the test."""
        super().tearDown()
        cache.clear()

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

    @override_settings(HOSTNAME="kokuworker")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_rate_limit_tasks(self, mock_inspect):
        """Test that single task cache creates and deletes a cache entry."""
        mock_inspect.reserved.return_value = {"celery@kokuworker": []}
        cache = WorkerCache()
        task_name = "test_task"
        task_args = [self.schema, "OCP", "1"]
        cache.lock_single_task(task_name, task_args)

        with patch("masu.processor.worker_cache.connection") as mock_conn:
            mock_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
            # mock_execute.return_value = 1
            self.assertFalse(rate_limit_tasks(task_name, self.schema))

        task_args = [self.schema, "OCP", "2"]
        cache.lock_single_task(task_name, task_args)

        with patch("masu.processor.worker_cache.connection") as mock_conn:
            mock_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (2,)
            self.assertTrue(rate_limit_tasks(task_name, self.schema))
