#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for running_celery_tasks endpoint."""
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
            r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB)
            r.flushall()

        if queue:
            LOG.info(f"Clearing tasks from {queue} queue")
            r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB)
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
