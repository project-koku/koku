from rest_framework import viewsets
from .sources_status import SourcesStatus
from .serializer import SourcesStatusSerializer
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from providers.aws.provider import AWSProvider
from api.provider.models import Provider, Sources
from providers.provider_access import ProviderAccessor, ProviderAccessorError
from unittest.mock import patch
from rest_framework.exceptions import ValidationError
class SourceStatusView(APIView):
    """SourceStatus view. This view assumes and requires that a provider already exists."""
    permission_classes = [AllowAny]
    def get(self, request, format=None):
        """
        Returns a list of Source Statuses.
        """
        source_id = self.request.query_params.get('source_id', None)
        source = Sources.objects.get(source_id=source_id)
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
        statuses = [source_ready]

        return Response(statuses)
