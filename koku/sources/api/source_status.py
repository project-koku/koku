from django.views.decorators.cache import never_cache
from rest_framework.decorators import (api_view,
                                       permission_classes,
                                       renderer_classes)

from rest_framework import viewsets
#from .sources_status import SourcesStatus
#from .serializer import SourcesStatusSerializer
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.settings import api_settings
from providers.aws.provider import AWSProvider
from api.provider.models import Provider, Sources
from providers.provider_access import ProviderAccessor, ProviderAccessorError
from unittest.mock import patch
from rest_framework.exceptions import ValidationError
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import status

@never_cache
@api_view(http_method_names=['GET'])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def source_status(request):
    """SourceStatus view. This view assumes that a provider and source already exist.

    Boolean Response of whether or not the Source is properly configured.

    The parameter source_id corresponds to the Table api_sources
    
    The Response boolean is True if cost_usage_source_ready does not throw an Exception.
    The Response boolean is False if cost_usage_source_ready throws a ValidationError.
    """

    source_id = request.query_params.get('source_id', None)
    if source_id is None:
        return Response(data='Missing query parameter source_id', status=status.HTTP_400_BAD_REQUEST)
    try:
        int(source_id)
    except ValueError:
        # source_id must be an integer
        return Response(data='source_id must be an integer', status=status.HTTP_400_BAD_REQUEST)
    try:
        source = Sources.objects.get(source_id=source_id)
    except ObjectDoesNotExist:
        # If the source isn't in our database, return False.
        return Response(False)
    source_billing_source = source.billing_source['bucket']
    source_authentication = source.authentication['resource_name']
    provider = source.source_type

    interface = ProviderAccessor(provider)
    source_ready = False
    try:
        source_ready = interface.cost_usage_source_ready(source_authentication, source_billing_source)
        source_ready = True
    except ValidationError:
        source_ready = False
    return Response(source_ready)
