# API views for manifests
from django.forms.models import model_to_dict
from django.utils.encoding import force_text
from rest_framework import permissions
from rest_framework import status
from rest_framework import viewsets
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from api.provider.models import Provider
from masu.api.manifest.serializers import ManifestSerializer
from masu.api.manifest.serializers import UsageReportStatusSerializer
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus


class ManifestPermission(permissions.BasePermission):
    """Determines if a user has access to Manifests APIs."""

    def has_permission(self, request, view):
        """Check permission based on the defined access."""
        return True


class ManifestException(APIException):
    """Invalid query value"""

    def __init__(self, message):
        """Initialize with status code 40."""
        self.status_code = status.HTTP_404_NOT_FOUND
        self.detail = {"detail": force_text(message)}


class ManifestView(viewsets.ModelViewSet):
    queryset = CostUsageReportManifest.objects.all()
    serializer_class = ManifestSerializer
    permission_classes = [ManifestPermission]
    http_method_names = ["get", "post", "head", "delete", "put"]

    def get_provider_UUID(request, provider):
        """Gets provider uuid based on provider name"""
        provider = Provider.objects.filter(name=provider).first()
        if provider is None:
            raise ManifestException("Invalid provider name.")
        return model_to_dict(provider)

    def set_pagination(self, request, queryset, serializer):
        page = self.paginate_queryset(queryset)
        if page is not None:
            serialized = serializer(page, many=True).data
            return serialized

    def list_all(self, request, *args, **kwargs):
        """API list all Manifests, filter by: provider name"""
        param = self.request.query_params
        if request.GET.get("name"):
            providers = self.get_provider_UUID(param["name"])
            queryset = self.queryset.filter(provider_id=providers["uuid"])
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            return Response(ManifestSerializer(queryset).data, many=True)
        else:
            return super().list(request)

    def retrieve(self, request, *args, **kwargs):
        """Get Manifests by source UUID"""
        sourceuuidParam = kwargs
        queryset = self.queryset.filter(provider_id=sourceuuidParam["source_uuid"])
        if not queryset:
            raise ManifestException("Invalid source uuid.")

        pagination = self.set_pagination(self, queryset, ManifestSerializer)
        if pagination is not None:
            return self.get_paginated_response(pagination)

        queryset = ManifestSerializer(queryset, many=True).data
        return Response(queryset)

    def retrieve_one(self, request, *args, **kwargs):
        """Get single Manifest by source UUID and manifest ID"""
        Params = kwargs
        queryset = self.queryset.filter(provider_id=Params["source_uuid"]).filter(id=Params["manifest_id"])
        if not queryset:
            raise ManifestException("Invalid source uuid or manifest id")
        queryset = self.get_serializer(queryset, many=True).data
        return Response(queryset)

    def get_manifest_files(self, request, *args, **kwargs):
        Params = kwargs
        queryset = CostUsageReportStatus.objects.filter(manifest_id=Params["manifest_id"])
        if not queryset:
            raise ManifestException("Invalid manifest id")

        pagination = self.set_pagination(self, queryset, UsageReportStatusSerializer)
        if pagination is not None:
            return self.get_paginated_response(pagination)

        queryset = UsageReportStatusSerializer(queryset, many=True).data
        return Response(queryset)

    def get_one_manifest_file(self, request, *args, **kwargs):
        Params = kwargs
        queryset = CostUsageReportStatus.objects.filter(manifest_id=Params["manifest_id"]).filter(id=Params["id"])
        if not queryset:
            raise ManifestException("Invalid manifest id or report status id")
        queryset = UsageReportStatusSerializer(queryset, many=True).data
        return Response(queryset)
