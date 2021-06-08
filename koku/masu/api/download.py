#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for temporary force download endpoint."""
from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from masu.celery.tasks import check_report_updates


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def download_report(request):
    """Return download file async task ID."""
    params = request.query_params
    provider_uuid = params.get("provider_uuid")
    bill_date = params.get("bill_date")
    async_download_result = check_report_updates.delay(provider_uuid=provider_uuid, bill_date=bill_date)
    return Response({"Download Request Task ID": str(async_download_result)})
