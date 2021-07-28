#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Cache of worker tasks currently running."""
import logging
import re

from django.conf import settings
from django.core.cache import caches

from koku import CELERY_INSPECT

TASK_CACHE_EXPIRE = 30
LOG = logging.getLogger(__name__)


def create_single_task_cache_key(task_name, task_args=None):
    """Create the cache key for a single task with optional task args."""
    cache_str = task_name
    if task_args:
        cache_str += ":"
        cache_str += ":".join(task_args)
    return cache_str


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
        self._hostname = settings.HOSTNAME
        self.add_worker_keys()
        self.remove_offline_worker_keys()

    @property
    def worker_cache_keys(self):
        """Return worker cache keys."""
        return self.cache.get("keys", set())

    @property
    def active_workers(self):
        """Return a list of active workers."""
        running_workers = []
        celery_inspect_instance = CELERY_INSPECT.reserved()
        if celery_inspect_instance:
            hosts = celery_inspect_instance.keys()
            for host in hosts:

                # Celery returns workers in the form of celery@hostname.
                hostname_pattern = r"[^@]*$"
                found = re.search(hostname_pattern, host)
                if found:
                    hostname = found.group()
                    running_workers.append(hostname)
        else:
            LOG.warning("Unable to get celery inspect instance.")
        return running_workers

    @property
    def worker_cache(self):
        """Return the value of the cache key."""
        return self.cache.get(settings.WORKER_CACHE_KEY, default=[], version=self._hostname)

    def add_worker_keys(self):
        """Add worker key verison to list of workers."""
        worker_keys = self.worker_cache_keys
        if self._hostname not in worker_keys:
            worker_keys.update((self._hostname,))
            self.cache.set("keys", worker_keys)

    def remove_worker_key(self, hostname):
        """Remove worker key verison to list of workers."""
        worker_keys = self.worker_cache_keys
        if hostname in worker_keys:
            worker_keys.remove(hostname)
            self.cache.set("keys", worker_keys)

    def remove_offline_worker_keys(self):
        """Remove worker key for offline workers."""
        worker_keys = self.worker_cache_keys
        running_workers = self.active_workers

        for worker in worker_keys:
            if worker not in running_workers:
                LOG.info(f"Removing old worker: {worker}")
                self.invalidate_host(worker)
                self.remove_worker_key(worker)

    def invalidate_host(self, host=None):
        """Invalidate the cache for a particular host."""
        if not host:
            host = self._hostname
        self.cache.delete(settings.WORKER_CACHE_KEY, version=host)

    def add_task_to_cache(self, task_key):
        """Add an entry to the cache for a task."""
        task_list = self.worker_cache
        task_list.append(task_key)
        self.cache.set(settings.WORKER_CACHE_KEY, task_list, version=self._hostname)
        LOG.debug(f"Added task key {task_key} to cache.")

    def remove_task_from_cache(self, task_key):
        """Remove an entry from the cache for a task."""
        task_list = self.worker_cache
        try:
            task_list.remove(task_key)
        except ValueError:
            pass
        else:
            self.cache.set(settings.WORKER_CACHE_KEY, task_list, version=self._hostname)
            LOG.debug(f"Removed task key {task_key} from cache.")

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

    def single_task_is_running(self, task_name, task_args=None):
        """Check for a single task key in the cache."""
        cache_str = create_single_task_cache_key(task_name, task_args)
        return True if self.cache.get(cache_str) else False

    def lock_single_task(self, task_name, task_args=None, timeout=None):
        """Add a cache entry for a single task to lock a specific task."""
        cache_str = create_single_task_cache_key(task_name, task_args)
        # Expire the cache so we don't infinite loop waiting
        if timeout:
            self.cache.add(cache_str, "true", timeout)
        else:
            self.cache.add(cache_str, "true", TASK_CACHE_EXPIRE)

    def release_single_task(self, task_name, task_args=None):
        """Delete the cache entry for a single task."""
        cache_str = create_single_task_cache_key(task_name, task_args)
        self.cache.delete(cache_str)
