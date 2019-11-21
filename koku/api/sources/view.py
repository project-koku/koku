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

"""View for Sources Proxy."""
import requests

import logging

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.cache import never_cache


from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny

from api.iam.models import Customer
from sources.api.serializers import SourcesSerializer
from api.provider.models import Sources


LOG = logging.getLogger(__name__)


class SourcesProxyViewSet(mixins.ListModelMixin,
                     mixins.RetrieveModelMixin,
                     mixins.UpdateModelMixin,
                     viewsets.GenericViewSet):
    """Sources View.

    A viewset that provides default `create()`, `retrieve()`,
    `update()`, and `list()` actions.
    """
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
        source_id = kwargs.get('source_id')
        url = f'{settings.SOURCES_CLIENT_BASE_URL}/sources/{source_id}/'
        r = requests.patch(url)
        response = HttpResponse(
            content=r.content,
            status=r.status_code,
            content_type=r.headers['Content-Type']
        )

        return response

    @never_cache
    def list(self, request, *args, **kwargs):
        """Obtain the list of sources."""
        url = f'{settings.SOURCES_CLIENT_BASE_URL}/sources/'
        r = requests.get(url)
        response = HttpResponse(
            content=r.content,
            status=r.status_code,
            content_type=r.headers['Content-Type']
        )

        return response

    @never_cache
    def retrieve(self, request, *args, **kwargs):
        """Get a source."""
        source_id = kwargs.get('source_id')
        url = f'{settings.SOURCES_CLIENT_BASE_URL}/sources/{source_id}/'
        r = requests.get(url)
        response = HttpResponse(
            content=r.content,
            status=r.status_code,
            content_type=r.headers['Content-Type']
        )

        return response

