#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for update_cost_model_costs endpoint."""
import logging

from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from koku import CELERY_INSPECT

LOG = logging.getLogger(__name__)


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def running_celery_tasks(request):
    """Get the task ids of running cerlery tasks."""
    active_dict = CELERY_INSPECT.active()
    active_tasks = []
    if active_dict:
        for task_list in active_dict.values():
            active_tasks.extend(task_list)
    if active_tasks:
        active_tasks = [dikt.get("id", "") for dikt in active_tasks]
    return Response({"active_tasks": active_tasks})
