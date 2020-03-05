#
# Copyright 2019 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""View for Sources."""
import logging

from django.conf import settings
from django.db import connection
from django.shortcuts import get_object_or_404
from django.utils.encoding import force_text
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
from api.iam.models import Tenant
from api.iam.serializers import create_schema_name
from api.provider.models import Sources
from api.provider.provider_manager import ProviderManager
from api.provider.provider_manager import ProviderManagerError
from sources.api import get_account_from_header
from sources.api import get_auth_header
from sources.api.serializers import AdminSourcesSerializer
from sources.api.serializers import SourcesSerializer
from sources.kafka_source_manager import KafkaSourceManager
from sources.storage import SourcesStorageError


class DestroySourceMixin(mixins.DestroyModelMixin):
    """A mixin for destroying a source."""

    @never_cache
    def destroy(self, request, *args, **kwargs):
        """Delete a source."""
        source = self.get_object()
        manager = KafkaSourceManager(get_auth_header(request))
        manager.destroy_provider(source.koku_uuid)
        response = super().destroy(request, *args, **kwargs)
        return response


LOG = logging.getLogger(__name__)
MIXIN_LIST = [mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet]


if settings.DEVELOPMENT:
    MIXIN_LIST.append(mixins.CreateModelMixin)
    MIXIN_LIST.append(DestroySourceMixin)


class SourceFilter(FilterSet):
    """Source custom filters."""

    name = CharListFilter(field_name="name", lookup_expr="name__icontains")
    type = CharListFilter(field_name="source_type", lookup_expr="source_type__iexact")

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

    @property
    def allowed_methods(self):
        """Return the list of allowed HTTP methods, uppercased."""
        if "put" in self.http_method_names:
            self.http_method_names.remove("put")
        return [method.upper() for method in self.http_method_names if hasattr(self, method)]

    def get_serializer_class(self):
        """Return the appropriate serializer depending on the method."""
        if self.request.method in (permissions.SAFE_METHODS, "PATCH"):
            return SourcesSerializer
        else:
            return AdminSourcesSerializer

    def get_queryset(self):
        """Get a queryset.

        Restricts the returned Sources to the associated account,
        by filtering against a `account_id` in the request.
        """
        queryset = Sources.objects.none()
        account_id = get_account_from_header(self.request)
        try:
            queryset = Sources.objects.filter(account_id=account_id)
        except Sources.DoesNotExist:
            LOG.error("No sources found for account id %s.", account_id)

        return queryset

    def get_object(self):
        queryset = self.get_queryset()
        queryset = self.filter_queryset(queryset)
        pk = self.kwargs.get("pk")
        try:
            uuid = UUIDField().to_internal_value(data=pk)
            obj = Sources.objects.get(source_uuid=uuid)
            if obj:
                return obj
        except ValidationError:
            pass
        obj = get_object_or_404(queryset, **{"pk": pk})
        self.check_object_permissions(self.request, obj)
        return obj

    def _get_account_and_tenant(self, request):
        """Get account_id and tenant from request."""
        account_id = get_account_from_header(request)
        schema_name = create_schema_name(account_id)
        tenant = tenant = Tenant.objects.get(schema_name=schema_name)
        return (account_id, tenant)

    @never_cache
    def update(self, request, *args, **kwargs):
        """Update a Source."""
        try:
            return super().update(request=request, args=args, kwargs=kwargs)
        except (SourcesStorageError, ParseError) as error:
            raise SourcesException(str(error))

    @never_cache
    def list(self, request, *args, **kwargs):
        """Obtain the list of sources."""
        response = super().list(request=request, args=args, kwargs=kwargs)
        _, tenant = self._get_account_and_tenant(request)
        for source in response.data["data"]:
            try:
                manager = ProviderManager(source["uuid"])
            except ProviderManagerError:
                source["provider_linked"] = False
            else:
                source["provider_linked"] = True
                source["infrastructure"] = manager.get_infrastructure_name()
                connection.set_tenant(tenant)
                source["cost_models"] = [
                    {"name": model.name, "uuid": model.uuid} for model in manager.get_cost_models(tenant)
                ]
                connection.set_schema_to_public()
        connection.set_schema_to_public()
        return response

    @never_cache
    def retrieve(self, request, *args, **kwargs):
        """Get a source."""
        response = super().retrieve(request=request, args=args, kwargs=kwargs)
        _, tenant = self._get_account_and_tenant(request)
        try:
            manager = ProviderManager(response.data["uuid"])
        except ProviderManagerError:
            response.data["provider_linked"] = False
        else:
            response.data["provider_linked"] = True
            response.data["infrastructure"] = manager.get_infrastructure_name()
            connection.set_tenant(tenant)
            response.data["cost_models"] = [
                {"name": model.name, "uuid": model.uuid} for model in manager.get_cost_models(tenant)
            ]
        connection.set_schema_to_public()
        return response

    @never_cache
    @action(methods=["get"], detail=True, permission_classes=[AllowAny])
    def stats(self, request, pk=None):
        """Get source stats."""
        account_id = get_account_from_header(request)
        schema_name = create_schema_name(account_id)
        source = self.get_object()
        stats = {}
        try:
            manager = ProviderManager(source.source_uuid)
        except ProviderManagerError:
            stats["provider_linked"] = False
        else:
            stats["provider_linked"] = True
            tenant = Tenant.objects.get(schema_name=schema_name)
            stats.update(manager.provider_statistics(tenant))
        return Response(stats)
