"""View to force the `upload_normalized_data` task to run."""
import logging

from django.views.decorators.cache import never_cache
from masu.celery import tasks
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

logger = logging.getLogger(__name__)


@never_cache
@api_view(http_method_names=["POST"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def upload_normalized_data(*args, **kwargs):
    """Run the upload_normalized_data task."""
    async_result = tasks.upload_normalized_data.delay()
    return Response({"AsyncResult ID": str(async_result)}, status=status.HTTP_201_CREATED)
