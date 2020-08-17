#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Test Cache of worker tasks currently running."""
import logging
from unittest.mock import patch

from django.core.cache import cache
from django.test.utils import override_settings

from masu.processor.worker_cache import WorkerCache
from masu.test import MasuTestCase

LOG = logging.getLogger(__name__)


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
