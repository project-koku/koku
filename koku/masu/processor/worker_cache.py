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
"""Cache of worker tasks currently running."""
import logging

from django.conf import settings
from django.core.cache import cache

LOG = logging.getLogger(__name__)


class WorkerCache:
    """A cache to track celery tasks across container/pod.

    The cache exists as a single Redis key. It is a complex object that can
    track multiple hosts running Celery and invalidate a single host's
    information when that host restarts. The values are keyed on the provider
    uuid and the billing month. This ensures that we are only ever running
    a single task for a provider and billing period at one time.

    Format: "worker" : {"{worker_host}": ["{provider_uuid}:{billing_month}],}

    Example: "worker" : {
        "koku-worker-0": ["10c0fb01-9d65-4605-bbf1-6089107ec5e5:2020-02-01 00:00:00],
        "koku-worker-1": ["10c0fb01-9d65-4605-bbf1-6089107ec5e5:2020-01-01 00:00:00],
    }

    """

    @property
    def worker_cache(self):
        """Return the value of the cache key."""
        _worker_cache = cache.get(settings.WORKER_CACHE_KEY)
        if not _worker_cache:
            _worker_cache = {}
            cache.set(settings.WORKER_CACHE_KEY, _worker_cache, timeout=None)
        return _worker_cache

    @property
    def host_specific_worker_cache(self):
        """Get the cached list of tasks."""
        return self.worker_cache.get(settings.HOSTNAME, [])

    def invalidate_host(self):
        """Invalidate the cache for a particular host."""
        _worker_cache = self.worker_cache
        _worker_cache[settings.HOSTNAME] = []
        cache.set(settings.WORKER_CACHE_KEY, _worker_cache, timeout=None)

    def set_host_specific_task_list(self, task_list):
        """Set the list of tasks in the cache."""
        _worker_cache = self.worker_cache
        _worker_cache[settings.HOSTNAME] = task_list
        cache.set(settings.WORKER_CACHE_KEY, _worker_cache, timeout=None)

    def add_task_to_cache(self, task_key):
        """Add an entry to the cache for a task."""
        task_list = self.host_specific_worker_cache
        task_list.append(task_key)
        self.set_host_specific_task_list(task_list)
        msg = f"Added {task_key} to cache."
        LOG.info(msg)

    def remove_task_from_cache(self, task_key):
        """Remove an entry from the cache for a task."""
        task_list = self.host_specific_worker_cache
        try:
            task_list.remove(task_key)
        except ValueError:
            pass
        else:
            self.set_host_specific_task_list(task_list)
            msg = f"Removed {task_key} from cache."
            LOG.info(msg)

    def get_all_running_tasks(self):
        """Combine each host's running tasks into a single list."""
        task_list = []
        for tasks in self.worker_cache.values():
            task_list.extend(tasks)
        return task_list

    def task_is_running(self, task_key):
        """Check if a task is in the cache."""
        task_list = self.get_all_running_tasks()
        return True if task_key in task_list else False
