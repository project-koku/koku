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

from django.conf import settings
from django.core.cache import cache

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

    def test_worker_cache(self):
        """Test the worker_cache property."""
        _worker_cache = WorkerCache().worker_cache
        self.assertEqual(_worker_cache, {})

    def test_host_specific_worker_cache(self):
        """Test the host specific cache."""
        _cache = WorkerCache()
        self.assertEqual(_cache.host_specific_worker_cache, [])

    def test_invalidate_host(self):
        """Test that a host's cache is invalidated."""
        task_list = [1, 2, 3]
        _cache = WorkerCache()

        _cache.set_host_specific_task_list(task_list)
        self.assertEqual(_cache.host_specific_worker_cache, task_list)

        _cache.invalidate_host()

        self.assertEqual(_cache.host_specific_worker_cache, [])

    def test_set_host_specific_task_list(self):
        """Test that setting a task list works."""
        task_list = [1, 2, 3]
        _cache = WorkerCache()

        self.assertEqual(_cache.host_specific_worker_cache, [])

        _cache.set_host_specific_task_list(task_list)
        self.assertEqual(_cache.host_specific_worker_cache, task_list)

    def test_add_task_to_cache(self):
        """Test that a single task is added."""
        task_list = [1, 2, 3]
        expected = [1, 2, 3, 4]
        _cache = WorkerCache()
        _cache.set_host_specific_task_list(task_list)
        self.assertEqual(_cache.host_specific_worker_cache, task_list)

        _cache.add_task_to_cache(4)
        self.assertEqual(_cache.host_specific_worker_cache, expected)

    def test_remove_task_from_cache(self):
        """Test that a task is removed."""
        task_list = [1, 2, 3, 4]
        expected = [1, 2, 3]
        _cache = WorkerCache()
        _cache.set_host_specific_task_list(task_list)
        self.assertEqual(_cache.host_specific_worker_cache, task_list)

        _cache.remove_task_from_cache(4)
        self.assertEqual(_cache.host_specific_worker_cache, expected)

    def test_remove_task_from_cache_value_not_in_cache(self):
        """Test that a task is removed."""
        task_list = [1, 2, 3, 4]
        _cache = WorkerCache()
        _cache.set_host_specific_task_list(task_list)
        self.assertEqual(_cache.host_specific_worker_cache, task_list)

        _cache.remove_task_from_cache(5)
        self.assertEqual(_cache.host_specific_worker_cache, task_list)

    def test_get_all_running_tasks(self):
        """Test that multiple hosts' task lists are combined."""
        second_host = "test"
        first_host_list = [1, 2, 3]
        second_host_list = [4, 5, 6]
        expected = first_host_list + second_host_list

        _cache = WorkerCache()
        _cache.set_host_specific_task_list(first_host_list)
        _worker_cache = _cache.worker_cache

        _worker_cache[second_host] = [4, 5, 6]
        cache.set(settings.WORKER_CACHE_KEY, _worker_cache, timeout=None)

        self.assertEqual(_cache.get_all_running_tasks(), expected)

    def test_task_is_running_true(self):
        """Test that a task is running."""
        task_list = [1, 2, 3]
        _cache = WorkerCache()
        _cache.set_host_specific_task_list(task_list)

        self.assertTrue(_cache.task_is_running(1))

    def test_task_is_running_false(self):
        """Test that a task is running."""
        task_list = [1, 2, 3]
        _cache = WorkerCache()
        _cache.set_host_specific_task_list(task_list)

        self.assertFalse(_cache.task_is_running(4))
