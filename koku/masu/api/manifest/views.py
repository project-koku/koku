#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Views for Masu API `manifest`."""
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.encoding import force_str
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
from masu.api.manifest.serializers import ManifestAndUsageReportSerializer
from masu.api.manifest.serializers import ManifestSerializer
from masu.api.manifest.serializers import UsageReportStatusSerializer
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus
from reporting_common.models import Status
from reporting_common.states import ManifestState
from reporting_common.states import ManifestStep


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
        self.detail = {"detail": force_str(message)}


class ManifestInvalidFilterException(APIException):
    """Invalid parameter value"""

    def __init__(self, message):
        """Initialize with status code 400."""
        self.status_code = status.HTTP_400_BAD_REQUEST
        self.detail = {"detail": force_str(message)}


def manifest_failed_filter(queryset, name, value):
    """A custom filter to return manfests that did or did not fail based on the boolean value of failed."""
    queryset = queryset.exclude(state__exact={})
    q_objects = None
    for step in ManifestStep:
        # if the failed field IS NULL then the manifest did not fail so we have to inverse the search criteria.
        new_q = Q(**{f"state__{step}__{ManifestState.FAILED}__isnull": not value})
        if q_objects:
            q_objects = q_objects | new_q
        else:
            q_objects = new_q
    return queryset.filter(q_objects)


def manifest_running_filter(queryset, name, value):
    """A custom filter to return manfests that are running tasks."""
    queryset = queryset.exclude(state__exact={})
    q_objects = None
    for step in ManifestStep:
        start_q = Q(**{f"state__{step}__{ManifestState.START}__isnull": False})
        finished_q = Q(**{f"state__{step}__time_taken_seconds__isnull": value})
        running_step_q = start_q & finished_q
        if q_objects:
            if value:
                q_objects = q_objects | running_step_q
            else:
                # Ensures all steps that started have finished
                q_objects = q_objects & running_step_q
        else:
            q_objects = running_step_q
    return queryset.filter(q_objects)


def manifest_started_filter(queryset, name, value):
    """A custom filter to return manifests that were created but have no state steps."""
    if value:
        queryset = queryset.exclude(state__exact={})
    else:
        queryset = queryset.filter(state__exact={})
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
    completed = DateFromToRangeFilter(field_name="completed_datetime")
    failed = BooleanFilter(method=manifest_failed_filter)
    running = BooleanFilter(method=manifest_running_filter)
    started = BooleanFilter(method=manifest_started_filter)

    class Meta:
        model = CostUsageReportManifest
        fields = [
            "provider",
            "account_id",
            "org_id",
            "schema_name",
            "created",
            "completed",
            "failed",
            "running",
            "started",
        ]


class UsageReportStatusFilter(FilterSet):
    """Custom Report Status filters."""

    status = ChoiceFilter(choices=Status.choices)

    class Meta:
        model = CostUsageReportStatus
        fields = [
            "status",
            "celery_task_id",
            "failed_status",
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
        serializer = ManifestAndUsageReportSerializer(data)
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
