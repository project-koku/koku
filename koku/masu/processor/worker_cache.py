#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Cache of worker tasks currently running."""
import base64
import logging
import pickle
import time

from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.db import DatabaseCache
from django.db import connection

from koku import CELERY_INSPECT
from koku.cache import CacheEnum

TASK_CACHE_EXPIRE = 30
# A worker that did not answer Celery inspect is dropped only after it has not been seen for this long.
WORKER_OFFLINE_GRACE_SECONDS = 600
WORKER_LAST_SEEN_KEY = "keys_last_seen"
LOG = logging.getLogger(__name__)


def _now():
    """Return the current time in seconds since the epoch."""
    return time.time()


def create_single_task_cache_key(task_name, task_args=None):
    """Create the cache key for a single task with optional task args."""
    cache_str = task_name
    if task_args:
        cache_str += ":"
        cache_str += ":".join(str(arg) for arg in task_args)
    return cache_str


def rate_limit_tasks(task_name, schema_name):
    """Limit the number of concurrent tasks for a customer.

    A lock counts only while the worker holding it is alive: a killed worker never
    releases its locks, and they would otherwise block the customer until they expire.
    """
    limit = settings.WORKER_CACHE_LARGE_CUSTOMER_CONCURRENT_TASKS
    lock_keys = _unexpired_lock_keys(task_name, schema_name)
    if len(lock_keys) < limit:
        return False

    live_workers = WorkerCache.cache.get("keys", set())
    if not live_workers:
        LOG.warning("No live worker list in the worker cache, counting every lock for %s", schema_name)
        return True

    held_locks = [key for key in lock_keys if _lock_is_held(key, live_workers)]
    return len(held_locks) >= limit


def _unexpired_lock_keys(task_name, schema_name):
    """Return the worker_cache_table keys of the unexpired locks of task_name for schema_name."""
    # The database cache deletes expired rows only occasionally, so they must not count as running tasks.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT cache_key FROM public.worker_cache_table "
            "WHERE cache_key LIKE %s AND cache_key LIKE %s AND expires > now()",
            [f"%{task_name}%", f"%{schema_name}%"],
        )
        return [row[0] for row in cursor.fetchall()]


def _lock_is_held(table_key, live_workers):
    """Return whether the lock stored under table_key belongs to one of live_workers.

    lock_single_task stores the worker's hostname under the default cache version. A row
    under another key format cannot be resolved and counts, as it did before.
    """
    prefix = WorkerCache.cache.make_key("")
    if not table_key.startswith(prefix):
        return True
    return WorkerCache.cache.get(table_key[len(prefix) :]) in live_workers


def _delete_if_value(cache, key, expected):
    """Delete key only if it currently stores expected. Return True if a value was removed.

    Production uses DatabaseCache, so the compare-and-delete is one SQL statement. Other
    backends fall back to get-then-delete, which is enough for sequential LocMemCache tests.
    """
    if isinstance(cache, DatabaseCache):
        table_key = cache.make_and_validate_key(key)
        encoded = base64.b64encode(pickle.dumps(expected, DatabaseCache.pickle_protocol)).decode("latin1")
        quote_name = connection.ops.quote_name
        table = f"{quote_name('public')}.{quote_name(cache._table)}"
        with connection.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {table} WHERE {quote_name('cache_key')} = %s AND {quote_name('value')} = %s",
                [table_key, encoded],
            )
            return cursor.rowcount > 0
    if cache.get(key) != expected:
        return False
    cache.delete(key)
    return True


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

    cache = caches[CacheEnum.worker]

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
                hostname = host.split("@", 1)[-1]
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
        """Remove the keys of workers not seen in Celery inspect replies for WORKER_OFFLINE_GRACE_SECONDS.

        Celery inspect stops collecting replies after a second without one, so a busy worker
        can miss a round. Without any reply the live workers are unknown and nothing is removed.
        """
        running_workers = self.active_workers
        if not running_workers:
            LOG.info("No Celery inspect replies, keeping all worker keys")
            return

        now = _now()
        last_seen = self.cache.get(WORKER_LAST_SEEN_KEY, {})
        for worker in {*running_workers, self._hostname}:
            last_seen[worker] = now
        for worker in self.worker_cache_keys:
            # Workers registered before last-seen tracking start their grace period now.
            last_seen.setdefault(worker, now)
            if now - last_seen[worker] > WORKER_OFFLINE_GRACE_SECONDS:
                LOG.info(f"Removing old worker: {worker}")
                self.invalidate_host(worker)
                self.remove_worker_key(worker)
        recent = {worker: seen for worker, seen in last_seen.items() if now - seen <= WORKER_OFFLINE_GRACE_SECONDS}
        self.cache.set(WORKER_LAST_SEEN_KEY, recent)

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
        return task_key in task_list

    def single_task_is_running(self, task_name, task_args=None):
        """Check for a single task key in the cache."""
        cache_str = create_single_task_cache_key(task_name, task_args)
        host = self.cache.get(cache_str)
        return host and host in self.worker_cache_keys

    def lock_single_task(self, task_name, task_args=None, timeout=TASK_CACHE_EXPIRE):
        """Add a cache entry for a single task to lock a specific task."""
        cache_str = create_single_task_cache_key(task_name, task_args)
        # Expire the cache so we don't infinite loop waiting
        self.cache.set(cache_str, self._hostname, timeout)

    def try_lock_single_task(self, task_name, task_args=None, timeout=TASK_CACHE_EXPIRE):
        """Acquire a single-task lock. Return True if this worker holds it.

        A live owner rejects the caller. A stale owner is removed only if that hostname
        is still stored, so two takeovers of the same lease cannot both succeed.
        """
        cache_str = create_single_task_cache_key(task_name, task_args)
        host = self.cache.get(cache_str)
        if host and host in self.worker_cache_keys:
            return False
        if host:
            _delete_if_value(self.cache, cache_str, host)
        return self.cache.add(cache_str, self._hostname, timeout)

    def release_single_task(self, task_name, task_args=None):
        """Delete the cache entry for a single task if this worker still owns it."""
        cache_str = create_single_task_cache_key(task_name, task_args)
        _delete_if_value(self.cache, cache_str, self._hostname)
