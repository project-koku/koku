#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for running_celery_tasks endpoint."""
import base64
import json
import logging

import redis
from django.conf import settings
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from koku import CELERY_INSPECT
from koku.celery import app
from masu.celery.tasks import collect_queue_metrics
from masu.celery.tasks import get_celery_queue_items
from masu.prometheus_stats import QUEUES

LOG = logging.getLogger(__name__)


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def running_celery_tasks(request):
    """Get the task ids of running celery tasks."""
    active_dict = CELERY_INSPECT.active()
    active_tasks = []
    if active_dict:
        for task_list in active_dict.values():
            active_tasks.extend(task_list)
    if active_tasks:
        active_tasks = [dikt.get("id", "") for dikt in active_tasks]
    return Response({"active_tasks": active_tasks})


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def celery_queue_lengths(request):
    """Get the length of the celery queues."""
    queue_len = collect_queue_metrics()
    LOG.info(f"Celery queue backlog info: {queue_len}")
    return Response(queue_len)


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def clear_celery_queues(request):
    """
    Clear celery queues.

    Args:
        clear_all (bool): optional boolean to all clearing all queues with redis
    Returns:
        purged_tasks (int): number of tasks deleted
    """

    clear_all = False
    purged_tasks = 0
    if request.method == "GET":
        params = request.query_params
        clear_all = params.get("clear_all")
        queue = params.get("queue")

        # clear all queues
        if clear_all:
            # clear default_celery queue
            purged_tasks = app.control.purge()
            LOG.info(f"Clearing all queues parameter: {clear_all}")
            queue_lengths = list(collect_queue_metrics().values())
            purged_tasks += sum(queue_lengths)
            r = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                username=settings.REDIS_USERNAME,
                password=settings.REDIS_PASSWORD,
                ssl=settings.REDIS_SSL,
                **settings.REDIS_CONNECTION_POOL_KWARGS,
            )
            r.flushall()

        if queue:
            LOG.info(f"Clearing tasks from {queue} queue")
            r = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                username=settings.REDIS_USERNAME,
                password=settings.REDIS_PASSWORD,
                ssl=settings.REDIS_SSL,
                **settings.REDIS_CONNECTION_POOL_KWARGS,
            )
            queue_lengths = collect_queue_metrics().get(queue)
            purged_tasks += queue_lengths
            r.delete(queue)

        LOG.info(f"Celery purged tasks: {purged_tasks}")
        return Response({"purged_tasks": purged_tasks})


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def celery_queue_tasks(request):
    """Get the task info of queued celery tasks."""
    params = request.query_params
    queue = params.get("queue", None)
    if queue and queue not in QUEUES:
        errmsg = "Must provide a valid queue to search."
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
    task = params.get("task", None)
    tasks_list = get_celery_queue_items(queue_name=queue, task_name=task)
    return Response({"queued_tasks": tasks_list})


def _redis_client():
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        username=settings.REDIS_USERNAME,
        password=settings.REDIS_PASSWORD,
        ssl=settings.REDIS_SSL,
        **settings.REDIS_CONNECTION_POOL_KWARGS,
    )


def _task_identity(message):
    """Return (task name, args, kwargs, embed) of a queued Celery message, or None if it cannot be read.

    Everything comes from the message body: the argsrepr/kwargsrepr headers
    are truncated by Celery and could make different tasks look identical.
    The embed holds chained/linked follow-up tasks, so copies that would
    start different follow-ups are not duplicates.
    """
    try:
        envelope = json.loads(message)
        task = envelope["headers"]["task"]
        body = envelope["body"]
        if envelope.get("properties", {}).get("body_encoding") == "base64":
            body = base64.b64decode(body)
        args, kwargs, embed = json.loads(body)
    except (TypeError, ValueError, KeyError, AttributeError):
        return None
    return (
        task,
        json.dumps(args, sort_keys=True),
        json.dumps(kwargs, sort_keys=True),
        json.dumps(embed, sort_keys=True),
    )


def _task_id(message):
    return json.loads(message)["headers"].get("id")


@never_cache
@api_view(http_method_names=["GET", "DELETE"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def deduplicate_celery_queue(request):
    """Find (GET) or remove (DELETE) exact duplicate tasks in a Celery queue.

    Tasks are duplicates when the task name, args, kwargs and chained follow-up
    tasks are identical (kwargs include the manifest and tracing ids). One copy
    of each is kept: the one closest to the consuming end of the list (kombu
    pushes with LPUSH and workers pop with BRPOP, so the right end runs first).
    Extra copies are removed by their exact message with LREM, so messages taken
    by a worker in the meantime are simply not found.

    Positions in the response count from the consuming end: 0 runs next.
    """
    queue = request.query_params.get("queue")
    if queue not in QUEUES:
        return Response({"Error": "Must provide a valid queue."}, status=status.HTTP_400_BAD_REQUEST)

    client = _redis_client()
    messages = client.lrange(queue, 0, -1)
    unreadable = 0
    groups = {}
    for position, message in enumerate(reversed(messages)):
        identity = _task_identity(message)
        if identity is None:
            unreadable += 1
            continue
        groups.setdefault(identity, []).append((position, message))
    duplicated = {identity: copies for identity, copies in groups.items() if len(copies) > 1}

    simulate = request.method != "DELETE"
    removed = 0
    duplicated_tasks = []
    summary = {}
    for (name, args, kwargs, embed), (kept, *extra) in sorted(duplicated.items(), key=lambda item: -len(item[1])):
        entry = {
            "name": name,
            "args": json.loads(args),
            "kwargs": json.loads(kwargs),
            "extra_copies": len(extra),
            "kept": {"id": _task_id(kept[1]), "position": kept[0]},
            "copies": [{"id": _task_id(message), "position": position} for position, message in extra],
        }
        follow_up = json.loads(embed)
        if isinstance(follow_up, dict) and any(follow_up.values()):
            entry["follow_up"] = follow_up
        if not simulate:
            entry["removed_ids"], entry["not_found_ids"] = [], []
            for _, message in extra:
                task_id = _task_id(message)
                if client.lrem(queue, 1, message):
                    removed += 1
                    entry["removed_ids"].append(task_id)
                    LOG.info(f"Removed duplicate task {name}[{task_id}] from {queue}: args={args} kwargs={kwargs}")
                else:
                    entry["not_found_ids"].append(task_id)
        duplicated_tasks.append(entry)
        totals = summary.setdefault(name, {"duplicated_tasks": 0, "extra_copies": 0})
        totals["duplicated_tasks"] += 1
        totals["extra_copies"] += len(extra)

    duplicates = sum(entry["extra_copies"] for entry in duplicated_tasks)
    if not simulate:
        LOG.info(f"Removed {removed} duplicate tasks from {queue} ({duplicates} found)")
    return Response(
        {
            "queue": queue,
            "queued": len(messages),
            "unreadable": unreadable,
            "duplicates": duplicates,
            "removed": removed,
            "simulate": simulate,
            "summary": summary,
            "duplicated_tasks": duplicated_tasks,
        }
    )
