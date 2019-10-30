from rest_framework import viewsets
from sources_status import SourcesStatus
from serializer import SourcesStatusSerializer


class SourceStatusViewSet(viewsets.ReadOnlyModelViewSet):
    """SourceStatus view set."""

    queryset = SourcesStatus.objects.all()
    serializer_class = SourcesStatusSerializer
