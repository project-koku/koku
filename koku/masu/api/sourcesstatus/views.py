from rest_framework import viewsets
from .sources_status import SourcesStatus
from .serializer import SourcesStatusSerializer
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response


class SourceStatusView(APIView):
    """SourceStatus view."""
    permission_classes = [AllowAny]
    def get(self, request, format=None):
        """
        Returns a list of Source Statuses.
        """
        statuses = [True, True, False]
        return Response(statuses)
