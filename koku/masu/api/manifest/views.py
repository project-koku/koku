#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Views for Masu API `manifest`."""
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
        """Initialize with status code 404."""
        self.status_code = status.HTTP_404_NOT_FOUND
        self.detail = {"detail": force_text(message)}


class ManifestInvalidFilterException(APIException):
    """Invalid parameter value"""

    def __init__(self, message):
        """Initialize with status code 400."""
        self.status_code = status.HTTP_400_BAD_REQUEST
        self.detail = {"detail": force_text(message)}


class ManifestView(viewsets.ModelViewSet):
    """Manifest View class."""

    queryset = CostUsageReportManifest.objects.all().order_by("-manifest_creation_datetime")
    serializer_class = ManifestSerializer
    permission_classes = [ManifestPermission]
    http_method_names = ["get"]

    def get_provider_UUID(request, provider):
        """returns provider uuid based on provider name"""
        provider = Provider.objects.filter(name=provider).first()
        if provider is None:
            raise ManifestException("Invalid provider name.")
        return model_to_dict(provider)

    @staticmethod
    def check_filters(dict_):
        """Check if filter parameters are valid"""
        valid_query_params = ["name", "limit", "offset", "timestamp"]
        params = {k: dict_.get(k) for k in dict_.keys() if k not in valid_query_params}

        if params:
            raise ManifestInvalidFilterException("Invalid Filter Parameter")

    def set_pagination(self, request, queryset, serializer):
        """Sets up pagination"""
        page = self.paginate_queryset(queryset)
        if page is not None:
            serialized = serializer(page, many=True).data
            return serialized

    def get_all_manifests(self, request, *args, **kwargs):
        """API list all Manifests, filter by: provider name"""
        param = self.request.query_params
        self.check_filters(param.dict())
        response = None
        if request.GET.get("name"):
            providers = self.get_provider_UUID(param["name"])
            self.queryset = self.queryset.filter(provider_id=providers["uuid"])
            pagination = self.set_pagination(self, self.queryset, ManifestSerializer)
            response = self.check_pagnation(pagination)
        if request.GET.get("timestamp") == "asc":
            self.queryset = self.queryset.order_by("manifest_creation_datetime")
            pagination = self.set_pagination(self, self.queryset, ManifestSerializer)
            response = self.check_pagnation(pagination)
        if response is not None:
            return response
        else:
            return super().list(request)

    def check_pagnation(self, pagination):
        if pagination is not None:
            return self.get_paginated_response(pagination)
        else:
            return Response(ManifestSerializer(self.queryset).data, many=True)

    def get_manifests_by_source(self, request, *args, **kwargs):
        """Get Manifests by source UUID"""
        sourceuuidParam = kwargs
        try:
            queryset = self.queryset.filter(provider_id=sourceuuidParam["source_uuid"])
        except Exception:
            raise ManifestException("Invalid source uuid.")

        pagination = self.set_pagination(self, queryset, ManifestSerializer)
        if pagination is not None:
            return self.get_paginated_response(pagination)

        queryset = ManifestSerializer(queryset, many=True).data
        return Response(queryset)

    def get_manifest(self, request, *args, **kwargs):
        """Get single Manifest by source uuid and manifest id"""
        Params = kwargs
        try:
            queryset = self.queryset.filter(provider_id=Params["source_uuid"]).filter(id=Params["manifest_id"])
            if not queryset:
                raise ManifestException("Invalid manifest id")
        except Exception:
            raise ManifestException("Invalid source uuid")
        queryset = self.get_serializer(queryset, many=True).data
        return Response(queryset)

    def get_manifest_files(self, request, *args, **kwargs):
        """Get files for specific manifest"""
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
        """Get specified file for specific manifest"""
        Params = kwargs
        queryset = CostUsageReportStatus.objects.filter(manifest_id=Params["manifest_id"]).filter(id=Params["id"])
        if not queryset:
            raise ManifestException("Invalid manifest id or report status id")
        queryset = UsageReportStatusSerializer(queryset, many=True).data
        return Response(queryset)
