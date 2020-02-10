"""Views for user-initiated data exports."""
from rest_framework import mixins
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from api.dataexport.models import DataExportRequest
from api.dataexport.serializers import DataExportRequestSerializer


class DataExportRequestViewSet(
    mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    """Create, retrieve, or list data export requests."""

    queryset = DataExportRequest.objects.all()
    serializer_class = DataExportRequestSerializer
    permission_classes = (AllowAny,)
    lookup_field = "uuid"

    def get_queryset(self):
        """Get a queryset that only displays the user's data export requests."""
        user = self.request.user
        queryset = self.queryset.filter(created_by=user)
        return queryset
