#
# Copyright 2018 Red Hat, Inc.
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
"""View for Providers."""
import logging

from django.shortcuts import get_object_or_404
from django.utils.encoding import force_text
from django.views.decorators.cache import never_cache
from django_filters import FilterSet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins
from rest_framework import status
from rest_framework import viewsets
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.serializers import UUIDField

from .provider_manager import ProviderManager
from .provider_manager import ProviderManagerError
from api.common.filters import CharListFilter
from api.iam.models import Customer
from api.provider import serializers
from api.provider.models import Provider
from api.query_params import get_tenant


LOG = logging.getLogger(__name__)


class ProviderFilter(FilterSet):
    """Provider custom filters."""

    name = CharListFilter(field_name="name", lookup_expr="name__icontains")
    type = CharListFilter(field_name="type", lookup_expr="type__iexact")

    class Meta:
        model = Provider
        fields = ["type", "name"]


class ProviderDeleteException(APIException):
    """Provider deletion custom internal error exception."""

    default_detail = "Error removing provider"

    def __init__(self):
        """Initialize with status code 500."""
        super().__init__()
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        self.detail = {"detail": force_text(self.default_detail)}


class ProviderUpdateException(APIException):
    """Provider update custom internal error exception."""

    default_detail = "Error updating provider"

    def __init__(self):
        """Initialize with status code 500."""
        super().__init__()
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        self.detail = {"detail": force_text(self.default_detail)}


class ProviderMethodException(APIException):
    """General Exception class for Provider errors."""

    def __init__(self, message):
        """Set custom error message for Provider errors."""
        self.status_code = status.HTTP_405_METHOD_NOT_ALLOWED
        self.detail = {"detail": force_text(message)}


class ProviderBadRequestException(APIException):
    """General Exception class for Provider errors."""

    def __init__(self, message):
        """Set custom error message for Provider errors."""
        self.status_code = status.HTTP_400_BAD_REQUEST
        self.detail = {"detail": force_text(message)}


class ProviderViewSet(
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Provider View.

    A viewset that provides default `create()`, `retrieve()`,
    `update()`, and `list()` actions.
    """

    lookup_field = "uuid"
    queryset = Provider.objects.all()
    permission_classes = (AllowAny,)
    filter_backends = (DjangoFilterBackend,)
    filterset_class = ProviderFilter

    def get_serializer_class(self):
        """Return the appropriate serializer depending on user."""
        if "schema_name" in self.request.META.get("QUERY_STRING", ""):
            return serializers.AdminProviderSerializer
        else:
            return serializers.ProviderSerializer

    def get_queryset(self):
        """Get a queryset.

        Restricts the returned Providers to the associated account,
        by filtering against a `user` object in the request.
        """
        queryset = Provider.objects.none()
        stats = self.request.query_params.get("stats", "false").lower()
        if stats not in ["false", "true"]:
            raise ProviderBadRequestException(
                f"The stat parameter was set to {stats} but can be either 'false' or 'true'."
            )
        user = self.request.user
        if user:
            try:
                queryset = Provider.objects.filter(customer=user.customer)
            except Customer.DoesNotExist:
                LOG.error("No customer found for user %s.", user)
        return queryset

    @never_cache
    def create(self, request, *args, **kwargs):
        """Create a Provider."""
        provider_type = request.data.get("type")
        if (
            provider_type
            and Provider.PROVIDER_CASE_MAPPING.get(provider_type.lower())
            and provider_type != provider_type.lower()
        ):
            request.data["type"] = request.data.get("type", "").lower()
        return super().create(request=request, args=args, kwargs=kwargs)

    @never_cache
    def update(self, request, *args, **kwargs):
        """Update a Provider."""
        provider_type = request.data.get("type")
        if (
            provider_type
            and Provider.PROVIDER_CASE_MAPPING.get(provider_type.lower())
            and provider_type != provider_type.lower()
        ):
            request.data["type"] = provider_type.lower()
        if request.method == "PATCH":
            raise ProviderMethodException("PATCH not supported")
        user = request.user
        uuid = UUIDField().to_internal_value(data=kwargs.get("uuid"))
        get_object_or_404(Provider, uuid=uuid, customer=user.customer)

        manager = ProviderManager(kwargs["uuid"])
        try:
            manager.update(request)
        except ProviderManagerError as error:
            LOG.error(f"{request.user} failed to update provider uuid: {uuid}. Error: {str(error)}")
            raise ProviderUpdateException

        return super().update(request=request, args=args, kwargs=kwargs)

    @never_cache
    def list(self, request, *args, **kwargs):
        """Obtain the list of providers."""
        response = super().list(request=request, args=args, kwargs=kwargs)
        stats = request.query_params.get("stats", "false").lower()
        for provider in response.data["data"]:
            manager = ProviderManager(provider["uuid"])
            tenant = get_tenant(request.user)
            if stats == "true":
                provider["stats"] = manager.provider_statistics(tenant)
            provider["infrastructure"] = manager.get_infrastructure_name()
            provider["cost_models"] = [
                {"name": model.name, "uuid": model.uuid} for model in manager.get_cost_models(tenant)
            ]
        return response

    @never_cache
    def retrieve(self, request, *args, **kwargs):
        """Get a provider."""
        response = super().retrieve(request=request, args=args, kwargs=kwargs)
        stats = request.query_params.get("stats", "false").lower()
        tenant = get_tenant(request.user)
        manager = ProviderManager(kwargs["uuid"])
        response.data["infrastructure"] = manager.get_infrastructure_name()
        if stats == "true":
            response.data["stats"] = manager.provider_statistics(tenant)
        response.data["cost_models"] = [
            {"name": model.name, "uuid": model.uuid} for model in manager.get_cost_models(tenant)
        ]
        return response

    @never_cache
    def destroy(self, request, *args, **kwargs):
        """Delete a provider."""
        # throws ValidationError if pk is not a valid UUID
        user = request.user
        uuid = UUIDField().to_internal_value(data=kwargs.get("uuid"))
        get_object_or_404(Provider, uuid=uuid, customer=user.customer)

        manager = ProviderManager(uuid)
        try:
            manager.remove(request)
        except Exception as error:
            LOG.error(f"{request.user} failed to remove provider uuid: {uuid}. Error: {str(error)}")
            raise ProviderDeleteException

        return Response(status=status.HTTP_204_NO_CONTENT)
