#
# Copyright 2022 Red Hat Inc.
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

from masu.celery.tasks import check_cost_model_status


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def notification(request):
    """Return download file async task ID."""
    params = request.query_params
    provider_uuid = params.get("provider_uuid")
    async_notification_result = check_cost_model_status.delay(provider_uuid=provider_uuid)
    return Response({"Notification Request Task ID": str(async_notification_result)})
