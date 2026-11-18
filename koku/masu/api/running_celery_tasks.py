#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for running_celery_tasks endpoint."""
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
@api_view(http_method_names=["GET", "DELETE"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def celery_queue_tasks(request):
    """Get queued Celery task info, or remove one queued task by ID."""
    params = request.query_params
    queue = params.get("queue", None)
    if queue and queue not in QUEUES:
        errmsg = "Must provide a valid queue to search."
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "DELETE":
        task_id = params.get("task_id", None)
        if not queue or not task_id:
            errmsg = "Must provide both queue and task_id."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        r = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            username=settings.REDIS_USERNAME,
            password=settings.REDIS_PASSWORD,
            ssl=settings.REDIS_SSL,
            **settings.REDIS_CONNECTION_POOL_KWARGS,
        )
        for message in r.lrange(queue, 0, -1):
            try:
                task_message = json.loads(message)
            except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                continue

            if not isinstance(task_message, dict):
                continue
            headers = task_message.get("headers")
            if not isinstance(headers, dict) or headers.get("id") != task_id:
                continue

            # LREM searches for this exact message in the current list order.
            # count=1 leaves any duplicate queue entries in place.
            removed = r.lrem(queue, 1, message)
            if not removed:
                return Response({"Error": "Task not found in queue."}, status=status.HTTP_404_NOT_FOUND)

            LOG.info("Removed one queued Celery task from %s queue (task_id=%s)", queue, task_id)
            return Response({"queue": queue, "task_id": task_id, "removed": True})

        return Response({"Error": "Task not found in queue."}, status=status.HTTP_404_NOT_FOUND)

    task = params.get("task", None)
    tasks_list = get_celery_queue_items(queue_name=queue, task_name=task)
    return Response({"queued_tasks": tasks_list})
