# API views for manifests
from rest_framework import viewsets
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny

from masu.api.manifest.serializers import ManifestSerializer
from reporting_common.models import CostUsageReportManifest


class ManifestView(viewsets.ModelViewSet):
    queryset = CostUsageReportManifest.objects.all()
    serializer_class = ManifestSerializer

    http_method_names = ["get", "post", "head", "delete", "put"]

    @permission_classes(AllowAny)
    def list(self, request):
        queryset = CostUsageReportManifest.objects.all()
        response = ManifestSerializer(queryset, many=True)
        return response.data
