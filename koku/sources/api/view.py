#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Sources."""
import logging

from django.conf import settings
from django.db import IntegrityError
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.utils.encoding import force_text
from django.views.decorators.cache import cache_page
from django.views.decorators.cache import never_cache
from django_filters import FilterSet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins
from rest_framework import permissions
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.exceptions import ParseError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.serializers import UUIDField
from rest_framework.serializers import ValidationError

from api.common.filters import CharListFilter
from api.common.pagination import ListPaginator
from api.common.permissions import RESOURCE_TYPE_MAP
from api.provider.models import Sources
from api.provider.provider_builder import ProviderBuilder
from api.provider.provider_manager import ProviderManager
from api.provider.provider_manager import ProviderManagerError
from koku.cache import invalidate_view_cache_for_tenant_and_cache_key
from koku.cache import SOURCES_CACHE_PREFIX
from masu.util.aws.common import get_available_regions
from sources.api.serializers import AdminSourcesSerializer
from sources.api.serializers import SourcesDependencyError
from sources.api.serializers import SourcesSerializer
from sources.storage import SourcesStorageError


class DestroySourceMixin(mixins.DestroyModelMixin):
    """A mixin for destroying a source."""

    @method_decorator(never_cache)
    def destroy(self, request, *args, **kwargs):
        """Delete a source."""
        schema_name = request.user.customer.schema_name
        account_number = request.user.customer.account_id
        org_id = request.user.customer.org_id
        source = self.get_object()
        manager = ProviderBuilder(request.user.identity_header.get("encoded"), account_number, org_id)
        for _ in range(5):
            try:
                manager.destroy_provider(source.koku_uuid)
            except IntegrityError as error:
                LOG.warning(f"Retrying Source delete due to error: {error}")
            except Exception as error:  # catch everything else. return immediately
                msg = f"Source removal resulted in UNKNOWN error: {type(error).__name__}: {error}"
                LOG.error(msg)
                return Response(msg, status=500)
            else:
                result = super().destroy(request, *args, **kwargs)
                invalidate_view_cache_for_tenant_and_cache_key(schema_name, SOURCES_CACHE_PREFIX)
                return result
        LOG.error("Failed to remove Source")
        return Response("Failed to remove Source", status=500)


LOG = logging.getLogger(__name__)
MIXIN_LIST = [mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet]
HTTP_METHOD_LIST = ["get", "head"]

if settings.DEVELOPMENT:
    MIXIN_LIST.extend([mixins.CreateModelMixin, mixins.UpdateModelMixin, DestroySourceMixin])
    HTTP_METHOD_LIST.extend(["post", "patch", "delete"])


class SourceFilter(FilterSet):
    """Source custom filters."""

    name = CharListFilter(field_name="name", lookup_expr="name__icontains")
    type = CharListFilter(field_name="source_type", lookup_expr="source_type__icontains")

    class Meta:
        model = Sources
        fields = ["source_type", "name"]


class SourcesException(APIException):
    """Authentication internal error exception."""

    def __init__(self, error_msg):
        """Initialize with status code 400."""
        super().__init__()
        self.status_code = status.HTTP_400_BAD_REQUEST
        self.detail = {"detail": force_text(error_msg)}


class SourcesDependencyException(APIException):
    """Dependency error exception."""

    def __init__(self, error_msg):
        """Initialize with status code 424."""
        super().__init__()
        self.status_code = status.HTTP_424_FAILED_DEPENDENCY
        self.detail = {"detail": force_text(error_msg)}


class SourcesViewSet(*MIXIN_LIST):
    """Sources View.

    A viewset that provides default `retrieve()`,
    `update()`, and `list()` actions.
    """

    lookup_fields = ("source_id", "source_uuid")
    queryset = Sources.objects.all()
    permission_classes = (AllowAny,)
    filter_backends = (DjangoFilterBackend,)
    filterset_class = SourceFilter
    http_method_names = HTTP_METHOD_LIST

    @action(methods=["get"], detail=False, permission_classes=[AllowAny], url_path="aws-s3-regions")
    def aws_s3_regions(self, request):
        regions = get_available_regions("s3")
        return ListPaginator(regions, request).paginated_response

    def get_serializer_class(self):
        """Return the appropriate serializer depending on the method."""
        if self.request.method in permissions.SAFE_METHODS:
            return SourcesSerializer
        else:
            return AdminSourcesSerializer

    @staticmethod
    def get_excludes(request):
        """Get excluded source types by access."""
        excludes = []
        keep = []
        if settings.ENHANCED_ORG_ADMIN and request.user.admin:
            return excludes
        resource_access = request.user.access
        if resource_access is None or not isinstance(resource_access, dict):
            for resource_type in RESOURCE_TYPE_MAP.keys():
                excludes.extend(RESOURCE_TYPE_MAP.get(resource_type))
            return list(set(excludes))
        for resource_type in RESOURCE_TYPE_MAP.keys():
            access_value = resource_access.get(resource_type)
            if access_value is None:
                excludes.extend(RESOURCE_TYPE_MAP.get(resource_type))
            elif not access_value.get("read", []):
                excludes.extend(RESOURCE_TYPE_MAP.get(resource_type))
            else:
                keep.extend(RESOURCE_TYPE_MAP.get(resource_type))

        excludes = list(set(excludes))
        keep = list(set(keep))

        for provider in keep:
            try:
                excludes.remove(provider)
            except ValueError:
                pass

        return excludes

    def get_queryset(self):
        """Get a queryset.

        Restricts the returned Sources to the associated org_id,
        by filtering against a `org_id` in the request.
        """
        queryset = Sources.objects.none()
        org_id = self.request.user.customer.org_id
        try:
            excludes = self.get_excludes(self.request)
            queryset = Sources.objects.filter(org_id=org_id).exclude(source_type__in=excludes)
        except Sources.DoesNotExist:
            LOG.error("No sources found for org id %s.", org_id)

        return queryset

    def get_object(self):
        queryset = self.get_queryset()
        queryset = self.filter_queryset(queryset)
        pk = self.kwargs.get("pk")
        try:
            uuid = UUIDField().to_internal_value(data=pk)
            org_id = self.request.user.customer.org_id
            obj = Sources.objects.get(org_id=org_id, source_uuid=uuid)
            if obj:
                return obj
        except (ValidationError, Sources.DoesNotExist):
            pass

        try:
            int(pk)
            obj = get_object_or_404(queryset, **{"pk": pk})
            self.check_object_permissions(self.request, obj)
        except ValueError:
            raise Http404

        return obj

    def _get_account_and_tenant(self, request):
        """Get account_id and tenant from request."""
        account_id = request.user.customer.account_id
        tenant = request.tenant
        return (account_id, tenant)

    @method_decorator(never_cache)
    def update(self, request, *args, **kwargs):
        """Update a Source."""
        schema_name = request.user.customer.schema_name
        try:
            result = super().update(request=request, args=args, kwargs=kwargs)
            invalidate_view_cache_for_tenant_and_cache_key(schema_name, SOURCES_CACHE_PREFIX)
            return result
        except (SourcesStorageError, ParseError) as error:
            raise SourcesException(str(error))
        except SourcesDependencyError as error:
            raise SourcesDependencyException(str(error))

    @method_decorator(cache_page(settings.CACHE_MIDDLEWARE_SECONDS, key_prefix=SOURCES_CACHE_PREFIX))
    def list(self, request, *args, **kwargs):
        """Obtain the list of sources."""

        response = super().list(request=request, args=args, kwargs=kwargs)
        _, tenant = self._get_account_and_tenant(request)
        for source in response.data["data"]:
            if (
                source.get("authentication")
                and source.get("authentication").get("credentials")
                and source.get("authentication").get("credentials").get("client_secret")
            ):
                del source["authentication"]["credentials"]["client_secret"]
            try:
                manager = ProviderManager(source["uuid"])
            except ProviderManagerError:
                source["provider_linked"] = False
                source["active"] = False
                source["paused"] = False
                source["current_month_data"] = False
                source["previous_month_data"] = False
                source["status"] = False
                source["has_data"] = False
                source["infrastructure"] = {}
                source["cost_models"] = []
                source["additional_context"] = {}
            else:
                source["provider_linked"] = True
                source["active"] = manager.get_active_status()
                source["paused"] = manager.get_paused_status()
                source["current_month_data"] = manager.get_current_month_data_exists()
                source["previous_month_data"] = manager.get_previous_month_data_exists()
                source["status"] = manager.get_state()
                source["has_data"] = manager.get_any_data_exists()
                source["infrastructure"] = manager.get_infrastructure_info()
                source["cost_models"] = [
                    {"name": model.name, "uuid": model.uuid} for model in manager.get_cost_models(tenant)
                ]
                source["additional_context"] = manager.get_additional_context()
        return response

    @method_decorator(never_cache)
    def retrieve(self, request, *args, **kwargs):
        """Get a source."""
        response = super().retrieve(request=request, args=args, kwargs=kwargs)
        _, tenant = self._get_account_and_tenant(request)

        if response.data.get("authentication", {}).get("credentials", {}).get("client_secret"):
            del response.data["authentication"]["credentials"]["client_secret"]
        try:
            manager = ProviderManager(response.data["uuid"])
        except ProviderManagerError:
            response.data["provider_linked"] = False
            response.data["active"] = False
            response.data["paused"] = False
            response.data["current_month_data"] = False
            response.data["previous_month_data"] = False
            response.data["status"] = False
            response.data["has_data"] = False
            response.data["infrastructure"] = {}
            response.data["cost_models"] = []
        else:
            response.data["provider_linked"] = True
            response.data["active"] = manager.get_active_status()
            response.data["paused"] = manager.get_paused_status()
            response.data["current_month_data"] = manager.get_current_month_data_exists()
            response.data["previous_month_data"] = manager.get_previous_month_data_exists()
            response.data["status"] = manager.get_state()
            response.data["has_data"] = manager.get_any_data_exists()

            response.data["infrastructure"] = manager.get_infrastructure_info()
            response.data["cost_models"] = [
                {"name": model.name, "uuid": model.uuid} for model in manager.get_cost_models(tenant)
            ]
        return response

    @method_decorator(never_cache)
    @action(methods=["get"], detail=True, permission_classes=[AllowAny])
    def stats(self, request, pk=None):
        """Get source stats."""
        source = self.get_object()
        stats = {}
        try:
            manager = ProviderManager(source.source_uuid)
        except ProviderManagerError:
            stats["provider_linked"] = False
        else:
            stats["provider_linked"] = True
            stats.update(manager.provider_statistics(request.tenant))
        return Response(stats)
