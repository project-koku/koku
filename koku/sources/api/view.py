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
from functools import reduce
from operator import and_

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.encoding import force_text
from django.views.decorators.cache import never_cache
from django_filters import CharFilter, FilterSet
from django_filters.filters import BaseCSVFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.serializers import UUIDField

from api.iam.models import Customer
from sources.api.serializers import SourcesSerializer
from api.provider.models import Sources
from api.query_params import get_tenant


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


class SourceDeleteException(APIException):
    """Source deletion custom internal error exception."""

    default_detail = 'Error removing source'

    def __init__(self):
        """Initialize with status code 500."""
        super().__init__()
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        self.detail = {'detail': force_text(self.default_detail)}


class SourceMethodException(APIException):
    """General Exception class for Provider errors."""

    def __init__(self, message):
        """Set custom error message for Provider errors."""
        self.status_code = status.HTTP_405_METHOD_NOT_ALLOWED
        self.detail = {'detail': force_text(message)}


class SourcesViewSet(mixins.ListModelMixin,
                     mixins.RetrieveModelMixin,
                     mixins.UpdateModelMixin,
                     viewsets.GenericViewSet):
    """Sources View.

    A viewset that provides default `create()`, `retrieve()`,
    `update()`, and `list()` actions.
    """

    serializer_class = SourcesSerializer
    lookup_field = 'source_id'
    queryset = Sources.objects.all()
    permission_classes = (AllowAny,)
    filter_backends = (DjangoFilterBackend,)

    def get_serializer_class(self):
        """Return the appropriate serializer depending on user."""
        return SourcesSerializer

    def get_queryset(self):
        """Get a queryset.

        Restricts the returned Providers to the associated account,
        by filtering against a `user` object in the request.
        """
        queryset = Sources.objects.none()
        user = self.request.user
        if user:
            try:
                # queryset = Sources.objects.filter(customer=user.customer)
                queryset = Sources.objects.all()
            except Customer.DoesNotExist:
                LOG.error('No customer found for user %s.', user)
        return queryset

    @never_cache
    def update(self, request, *args, **kwargs):
        """Update a Source."""

        return super().update(request=request, args=args, kwargs=kwargs)

    @never_cache
    def list(self, request, *args, **kwargs):
        """Obtain the list of sources."""
        response = super().list(request=request, args=args, kwargs=kwargs)

        return response

    @never_cache
    def retrieve(self, request, *args, **kwargs):
        """Get a source."""
        response = super().retrieve(request=request, args=args, kwargs=kwargs)

        return response

