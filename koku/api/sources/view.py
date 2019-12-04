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
import logging

import requests
from django.conf import settings
from django.http import HttpResponse
from django.utils.encoding import force_text
from django.views.decorators.cache import never_cache
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny

from api.provider.models import Sources


LOG = logging.getLogger(__name__)


class SourcesProxyException(APIException):
    """Provider update custom internal error exception."""

    default_detail = 'Error updating provider'

    def __init__(self, message):
        """Initialize with status code 500."""
        super().__init__()
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        self.detail = {'detail': force_text(message)}


class SourcesMethodException(APIException):
    """General Exception class for Sources errors."""

    def __init__(self, message):
        """Set custom error message for Sources errors."""
        self.status_code = status.HTTP_405_METHOD_NOT_ALLOWED
        self.detail = {'detail': force_text(message)}


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
    url = f'{settings.SOURCES_CLIENT_BASE_URL}/sources/'

    @never_cache
    def update(self, request, *args, **kwargs):
        """Update a Source."""
        if request.method == 'PUT':
            raise SourcesMethodException('PUT not supported')

        source_id = kwargs.get('source_id')
        url = f'{self.url}{source_id}/'
        try:
            r = requests.patch(url, json=request.data, headers=self.request.headers)
        except requests.exceptions.ConnectionError as error:
            raise SourcesProxyException(str(error))
        response = HttpResponse(
            content=r.content,
            status=r.status_code,
            content_type=r.headers['Content-Type']
        )

        return response

    @never_cache
    def list(self, request, *args, **kwargs):
        """Obtain the list of sources."""
        try:
            r = requests.get(self.url, headers=self.request.headers)
        except requests.exceptions.ConnectionError as error:
            raise SourcesProxyException(str(error))
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
        url = f'{self.url}{source_id}/'
        try:
            r = requests.get(url, headers=self.request.headers)
        except requests.exceptions.ConnectionError as error:
            raise SourcesProxyException(str(error))
        response = HttpResponse(
            content=r.content,
            status=r.status_code,
            content_type=r.headers['Content-Type']
        )

        return response
