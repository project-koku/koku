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
from django.core.cache import caches

LOG = logging.getLogger(__name__)


class WorkerCache:
    """A cache to track celery tasks across container/pod.

    Each worker has a cache_key in the form :{host}:worker. A set containing each
    cache_key is stored in a separate cache entry called 'keys'. The worker cache_keys
    stores a list of task_keys for the task the worker is running. The WorkerCache takes
    all the entries in the 'keys' cache to build the list of currently running tasks.

    The task_keys are keyed on the provider uuid and the billing month. This ensures that
    we are only ever running a single task for a provider and billing period at one time.

    Format: ":hostworker:" : "{provider_uuid}:{billing_month}"

    Example:

        cache_key               |                           value                              |        expires
        ":1:keys:               | {"koku-worker-1", "koku-worker2"}                            |        datetime
        ":koku-worker-0:worker" | ["10c0fb01-9d65-4605-bbf1-6089107ec5e5:2020-02-01 00:00:00"] |        datetime
        ":koku-worker-1:worker" | ["10c0fb01-9d65-4605-bbf1-6089107ec5e5:2020-01-01 00:00:00"] |        datetime

    """

    cache = caches["worker"]

    def __init__(self):
        self.add_worker_keys()

    @property
    def worker_cache_keys(self):
        """Return worker cache keys."""
        return self.cache.get("keys", set())

    @property
    def worker_cache(self):
        """Return the value of the cache key."""
        return self.cache.get(settings.WORKER_CACHE_KEY, default=[], version=settings.HOSTNAME)

    def add_worker_keys(self):
        """Add worker key verison to list of workers."""
        worker_keys = self.worker_cache_keys
        if settings.HOSTNAME not in worker_keys:
            worker_keys.update((settings.HOSTNAME,))
            self.cache.set("keys", worker_keys)

    def invalidate_host(self):
        """Invalidate the cache for a particular host."""
        self.cache.delete(settings.WORKER_CACHE_KEY, version=settings.HOSTNAME)

    def add_task_to_cache(self, task_key):
        """Add an entry to the cache for a task."""
        task_list = self.worker_cache
        task_list.append(task_key)
        self.cache.set(settings.WORKER_CACHE_KEY, task_list, version=settings.HOSTNAME)
        LOG.info(f"Added task key {task_key} to cache.")

    def remove_task_from_cache(self, task_key):
        """Remove an entry from the cache for a task."""
        task_list = self.worker_cache
        try:
            task_list.remove(task_key)
        except ValueError:
            pass
        else:
            self.cache.set(settings.WORKER_CACHE_KEY, task_list, version=settings.HOSTNAME)
            LOG.info(f"Removed task key {task_key} from cache.")

    def get_all_running_tasks(self):
        """Combine each host's running tasks into a single list."""
        tasks = []
        for key in self.worker_cache_keys:
            tasks.extend(self.cache.get(settings.WORKER_CACHE_KEY, default=[], version=key))
        return tasks

    def task_is_running(self, task_key):
        """Check if a task is in the cache."""
        task_list = self.get_all_running_tasks()
        return True if task_key in task_list else False
