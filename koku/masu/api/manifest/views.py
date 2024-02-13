#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Views for Masu API `manifest`."""
from django.forms.models import model_to_dict
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.encoding import force_text
from django_filters import BooleanFilter
from django_filters import ChoiceFilter
from django_filters import DateFromToRangeFilter
from django_filters import FilterSet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from api.common.filters import CharListFilter
from api.provider.models import Provider
from masu.api.manifest.serializers import CustomSerializer
from masu.api.manifest.serializers import ManifestSerializer
from masu.api.manifest.serializers import UsageReportStatusSerializer
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus
from reporting_common.models import ManifestState
from reporting_common.models import ManifestStep
from reporting_common.models import Status


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

    queryset = CostUsageReportManifest.objects.all().order_by("-creation_datetime")
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
            self.queryset = self.queryset.order_by("creation_datetime")
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


def manifest_failed_filter(queryset, name, value):
    """A custom filter to return manfests that did or did not fail based on the boolean value of failed."""
    filters = {}
    for step in ManifestStep:
        # if the failed field IS NULL then the manifest did not fail so we have to inverse the search criteria.
        filters[f"state__{step}__{ManifestState.FAILED}__isnull"] = not value
    return queryset.filter(**filters)


def manifest_running_filter(queryset, name, value):
    """A custom filter to return manfests that are running tasks."""
    for step in ManifestStep:
        queryset = queryset.filter(**{f"state__{step}__{ManifestState.END}__isnull": value})
    return queryset


class ManifestFilter(FilterSet):
    """Custom Manifest filters."""

    account_id = CharListFilter(
        field_name="provider__customer__account_id", lookup_expr="provider__customer__account_id__icontains"
    )
    org_id = CharListFilter(
        field_name="provider__customer__org_id", lookup_expr="provider__customer__org_id__icontains"
    )
    schema_name = CharListFilter(
        field_name="provider__customer__schema_name", lookup_expr="provider__customer__schema_name__icontains"
    )
    created = DateFromToRangeFilter(field_name="creation_datetime")
    updated = DateFromToRangeFilter(field_name="manifest_updated_datetime")
    completed = DateFromToRangeFilter(field_name="completed_datetime")
    manifest_failed = BooleanFilter(method=manifest_failed_filter)
    manifest_running = BooleanFilter(method=manifest_running_filter)

    class Meta:
        model = CostUsageReportManifest
        fields = [
            "provider",
            "account_id",
            "org_id",
            "schema_name",
            "created",
            "updated",
            "completed",
            "manifest_failed",
            "manifest_running",
        ]


class UsageReportStatusFilter(FilterSet):
    """Custom Report Status filters."""

    status = ChoiceFilter(choices=Status.choices)

    class Meta:
        model = CostUsageReportStatus
        fields = [
            "status",
            "manifest",
            "celery_task_id",
        ]


class ManifestStatusViewSet(viewsets.ReadOnlyModelViewSet):
    """A viewset for Manifests."""

    queryset = CostUsageReportManifest.objects.all()
    serializer_class = ManifestSerializer
    permission_classes = [ManifestPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ManifestFilter
    http_method_names = ["get"]

    def retrieve(self, request, pk=None):
        queryset = self.get_queryset()
        queryset = self.filter_queryset(queryset)
        try:
            obj = get_object_or_404(queryset, pk=pk)
        except ValueError:
            raise Http404
        failed_reports = list(CostUsageReportStatus.objects.filter(manifest_id=pk, status=Status.FAILED))
        data = {"manifest": obj, "failed_reports": failed_reports}
        serializer = CustomSerializer(data)
        return Response(serializer.data)

    @action(methods=["get"], detail=True, filterset_class=UsageReportStatusFilter)
    def reports(self, request, pk=None):
        """Get reports for a specified manifest."""
        queryset = self.filter_queryset(CostUsageReportStatus.objects.filter(manifest_id=pk).order_by("id"))
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = UsageReportStatusSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = UsageReportStatusSerializer(queryset, many=True)
        return Response(serializer.data)
