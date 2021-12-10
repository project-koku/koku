#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for running_celery_tasks endpoint."""
import logging

from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from hcs.tasks import collect_hcs_report_data

LOG = logging.getLogger(__name__)


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def hcs_report_data(request):
    params = request.query_params
    start_date = params.start_date
    end_date = params.end_date or None

    LOG.info("Calling collect_hcs_report_data async task.")

    async_result = collect_hcs_report_data(start_date, end_date)

    return Response({"Report Data Task ID": str(async_result)})
