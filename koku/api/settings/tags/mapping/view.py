#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import dataclasses

from django.db.models import Case
from django.db.models import UUIDField
from django.db.models import Value
from django.db.models import When
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common.pagination import ListPaginator
from api.common.permissions.settings_access import SettingsAccessPermission
from api.settings.tags.mapping.query_handler import Relationship
from api.settings.tags.mapping.serializers import AddChildSerializer
from api.settings.tags.mapping.serializers import TagMappingSerializer
from api.settings.tags.mapping.serializers import ViewOptionsSerializer
from api.settings.tags.mapping.utils import resummarize_current_month_by_tag_keys
from api.settings.tags.mapping.utils import retrieve_tag_rate_mapping
from api.settings.tags.mapping.utils import TagMappingFilters
from api.settings.tags.serializers import SettingsTagIDSerializer
from api.settings.utils import NonValidatedMultipleChoiceFilter
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.all.models import TagMapping


class CostModelAnnotationMixin:
    def get_annotated_queryset(self):
        when_conditions = []
        tag_rate_map = retrieve_tag_rate_mapping(self.request.user.customer.schema_name)
        for tag_key, tag_metadata in tag_rate_map.items():
            when_conditions.append(When(key=tag_key, then=Value(tag_metadata.get("cost_model_id"))))
        return self.get_queryset().annotate(cost_model_id=Case(*when_conditions, output_field=UUIDField()))


class SettingsTagMappingFilter(TagMappingFilters):
    source_type = NonValidatedMultipleChoiceFilter(field_name="parent__provider_type", method="filter_by_source_type")
    parent = NonValidatedMultipleChoiceFilter(field_name="parent__key", method="filter_by_key")
    child = NonValidatedMultipleChoiceFilter(field_name="child__key", method="filter_by_key")

    class Meta:
        model = TagMapping
        fields = ("parent", "child", "source_type")
        default_ordering = ["parent"]


class SettingsEnabledTagKeysFilter(TagMappingFilters):
    key = NonValidatedMultipleChoiceFilter(method="filter_by_key")
    source_type = NonValidatedMultipleChoiceFilter(field_name="provider_type", method="filter_by_source_type")

    class Meta:
        model = EnabledTagKeys
        fields = ("key", "source_type")
        default_ordering = ["key", "-enabled"]


class SettingsTagMappingView(generics.GenericAPIView):
    queryset = TagMapping.objects.all()
    serializer_class = TagMappingSerializer
    permission_classes = (SettingsAccessPermission,)
    filter_backends = (DjangoFilterBackend,)
    filterset_class = SettingsTagMappingFilter

    @method_decorator(never_cache)
    def get(self, request: Request, **kwargs):
        filtered_qset = self.filter_queryset(self.get_queryset())
        serializer = self.serializer_class(filtered_qset, many=True)
        relationships = Relationship.create_list_of_relationships(serializer.data)
        formatted_response = Response([dataclasses.asdict(item) for item in relationships])
        paginator = ListPaginator(formatted_response.data, request)
        response = paginator.paginated_response

        return response


class SettingsTagMappingChildView(CostModelAnnotationMixin, generics.GenericAPIView):
    queryset = (
        EnabledTagKeys.objects.exclude(parent__isnull=False).exclude(child__parent__isnull=False).filter(enabled=True)
    )
    serializer_class = ViewOptionsSerializer
    permission_classes = (SettingsAccessPermission,)
    filter_backends = (DjangoFilterBackend,)
    filterset_class = SettingsEnabledTagKeysFilter

    @method_decorator(never_cache)
    def get(self, request: Request, **kwargs):
        filtered_qset = self.filter_queryset(self.get_annotated_queryset())
        serializer = self.serializer_class(filtered_qset, many=True)
        paginator = ListPaginator(serializer.data, request)
        response = paginator.paginated_response

        return response


class SettingsTagMappingParentView(CostModelAnnotationMixin, generics.GenericAPIView):
    queryset = EnabledTagKeys.objects.exclude(child__parent__isnull=False).filter(enabled=True)
    serializer_class = ViewOptionsSerializer
    permission_classes = (SettingsAccessPermission,)
    filter_backends = (DjangoFilterBackend,)
    filterset_class = SettingsEnabledTagKeysFilter

    @method_decorator(never_cache)
    def get(self, request: Request, **kwargs):
        filtered_qset = self.filter_queryset(self.get_annotated_queryset())
        serializer = self.serializer_class(filtered_qset, many=True)
        paginator = ListPaginator(serializer.data, request)
        response = paginator.paginated_response

        return response


class SettingsTagMappingChildAddView(APIView):
    permission_classes = (SettingsAccessPermission,)

    def put(self, request):
        tag_rates = retrieve_tag_rate_mapping(request.user.customer.schema_name)
        serializer = AddChildSerializer(data=request.data, context=tag_rates)
        serializer.is_valid(raise_exception=True)
        parent_row = EnabledTagKeys.objects.get(uuid=serializer.data.get("parent"))
        children_rows = list(EnabledTagKeys.objects.filter(uuid__in=serializer.data.get("children")))
        tag_mappings = [TagMapping(parent=parent_row, child=child_row) for child_row in children_rows]
        TagMapping.objects.bulk_create(tag_mappings)
        resummarize_current_month_by_tag_keys(serializer.data.get("children", []), request.user.customer.schema_name)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SettingsTagMappingChildRemoveView(APIView):
    permission_classes = (SettingsAccessPermission,)

    def put(self, request: Request):
        children_uuids = request.data.get("ids", [])
        serializer = SettingsTagIDSerializer(data={"id_list": children_uuids})
        serializer.is_valid(raise_exception=True)
        if not TagMapping.objects.filter(child__uuid__in=children_uuids).exists():
            return Response({"detail": "Invalid children UUIDs."}, status=status.HTTP_400_BAD_REQUEST)
        TagMapping.objects.filter(child__in=children_uuids).delete()
        resummarize_current_month_by_tag_keys(children_uuids, request.user.customer.schema_name)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SettingsTagMappingParentRemoveView(APIView):
    permission_classes = (SettingsAccessPermission,)

    def put(self, request: Request):
        parents_uuid = request.data.get("ids", [])
        serializer = SettingsTagIDSerializer(data={"id_list": parents_uuid})
        serializer.is_valid(raise_exception=True)
        if not TagMapping.objects.filter(parent__uuid__in=parents_uuid).exists():
            return Response({"detail": "Invalid parents UUIDs."}, status=status.HTTP_400_BAD_REQUEST)
        # We should resummarize based on the child uuids since they were the ones replaced.
        child_uuids = list(TagMapping.objects.filter(parent__in=parents_uuid).values_list("child", flat=True))
        TagMapping.objects.filter(parent__in=parents_uuid).delete()
        resummarize_current_month_by_tag_keys(child_uuids, request.user.customer.schema_name)
        return Response(status=status.HTTP_204_NO_CONTENT)
