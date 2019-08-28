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
from functools import reduce
from operator import and_

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.encoding import force_text
from django_filters import CharFilter, FilterSet
from django_filters.filters import BaseCSVFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.serializers import UUIDField

from api.iam.models import Customer
from api.provider import serializers
from api.provider.models import Provider
from api.report.view import get_tenant
from .provider_manager import ProviderManager


LOG = logging.getLogger(__name__)


class CharListFilter(BaseCSVFilter, CharFilter):
    """Add query filter capability to provide an anded list of filter values."""

    def filter(self, qs, value):
        """Filter to create a composite and filter of the value list."""
        if not value:
            return qs
        value_list = ','.join(value).split(',')
        queries = [Q(**{self.lookup_expr: val}) for val in value_list]
        return qs.filter(reduce(and_, queries))


class ProviderFilter(FilterSet):
    """Provider custom filters."""

    name = CharListFilter(field_name='name', lookup_expr='name__icontains')

    class Meta:
        model = Provider
        fields = ['type', 'name']


class ProviderDeleteException(APIException):
    """Provider deletion custom internal error exception."""

    default_detail = 'Error removing provider'

    def __init__(self):
        """Initialize with status code 500."""
        super().__init__()
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        self.detail = {'detail': force_text(self.default_detail)}


class ProviderViewSet(mixins.CreateModelMixin,
                      mixins.DestroyModelMixin,
                      mixins.ListModelMixin,
                      mixins.RetrieveModelMixin,
                      viewsets.GenericViewSet):
    """Provider View.

    A viewset that provides default `create()`, `retrieve()`,
    and `list()` actions.
    """

    lookup_field = 'uuid'
    queryset = Provider.objects.all()
    permission_classes = (AllowAny,)
    filter_backends = (DjangoFilterBackend,)
    filterset_class = ProviderFilter

    def get_serializer_class(self):
        """Return the appropriate serializer depending on user."""
        if 'schema_name' in self.request.META.get('QUERY_STRING', ''):
            return serializers.AdminProviderSerializer
        else:
            return serializers.ProviderSerializer

    def get_queryset(self):
        """Get a queryset.

        Restricts the returned Providers to the associated account,
        by filtering against a `user` object in the request.
        """
        queryset = Provider.objects.none()
        user = self.request.user
        if user:
            try:
                queryset = Provider.objects.filter(customer=user.customer)
            except Customer.DoesNotExist:
                LOG.error('No customer found for user %s.', user)
        return queryset

    def create(self, request, *args, **kwargs):
        """Create a Provider."""
        return super().create(request=request, args=args, kwargs=kwargs)

    def list(self, request, *args, **kwargs):
        """Obtain the list of providers."""
        response = super().list(request=request, args=args, kwargs=kwargs)
        for provider in response.data['data']:
            manager = ProviderManager(provider['uuid'])
            tenant = get_tenant(request.user)
            provider['stats'] = manager.provider_statistics(tenant)
            provider['infrastructure'] = manager.get_infrastructure_name(tenant)
        return response

    def retrieve(self, request, *args, **kwargs):
        """Get a provider."""
        response = super().retrieve(request=request, args=args, kwargs=kwargs)
        tenant = get_tenant(request.user)
        manager = ProviderManager(kwargs['uuid'])
        response.data['infrastructure'] = manager.get_infrastructure_name(tenant)
        response.data['stats'] = manager.provider_statistics(tenant)
        return response

    def destroy(self, request, *args, **kwargs):
        """Delete a provider."""
        # throws ValidationError if pk is not a valid UUID
        user = request.user
        uuid = UUIDField().to_internal_value(data=kwargs.get('uuid'))
        get_object_or_404(Provider, uuid=uuid, customer=user.customer)

        # Block any users not part of the organization
        # if not self.get_queryset():
            # raise PermissionDenied()
        manager = ProviderManager(uuid)
        try:
            manager.remove(request.user)
        except Exception:
            LOG.error('{} failed to remove provider uuid: {}.'.format(request.user, uuid))
            raise ProviderDeleteException

        return Response(status=status.HTTP_204_NO_CONTENT)
