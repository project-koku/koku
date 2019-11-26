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
from base64 import b64decode
from json import loads as json_loads
from json.decoder import JSONDecodeError

from django.views.decorators.cache import never_cache
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, viewsets
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from sources.api.serializers import SourcesSerializer
from sources.api.source_status import SourceStatus

from api.provider.models import Sources


LOG = logging.getLogger(__name__)


class SourcesViewSet(mixins.ListModelMixin,
                     mixins.RetrieveModelMixin,
                     mixins.UpdateModelMixin,
                     viewsets.GenericViewSet):
    """Sources View.

    A viewset that provides default `retrieve()`,
    `update()`, and `list()` actions.
    """

    serializer_class = SourcesSerializer
    lookup_field = 'source_id'
    queryset = Sources.objects.all()
    permission_classes = (AllowAny,)
    filter_backends = (DjangoFilterBackend,)

    @property
    def allowed_methods(self):
        """Return the list of allowed HTTP methods, uppercased."""
        if 'put' in self.http_method_names:
            self.http_method_names.remove('put')
        return [method.upper() for method in self.http_method_names
                if hasattr(self, method)]

    def get_queryset(self):
        """Get a queryset.

        Restricts the returned Sources to the associated account,
        by filtering against a `account_id` in the request.
        """
        queryset = Sources.objects.none()
        auth_header = self.request.headers.get('X-Rh-Identity')
        if auth_header:
            try:
                decoded_rh_auth = b64decode(auth_header)
                json_rh_auth = json_loads(decoded_rh_auth)
                account_id = json_rh_auth.get('identity', {}).get('account_number')
                queryset = Sources.objects.filter(account_id=account_id)
            except Sources.DoesNotExist:
                LOG.error('No sources found for account id %s.', account_id)
            except JSONDecodeError as error:
                LOG.error(str(error))
                return

        return queryset

    @never_cache
    def update(self, request, *args, **kwargs):
        """Update a Source."""
        return super().update(request=request, args=args, kwargs=kwargs)

    @never_cache
    def list(self, request, *args, **kwargs):
        """Obtain the list of sources."""
        return super().list(request=request, args=args, kwargs=kwargs)

    @never_cache
    def retrieve(self, request, *args, **kwargs):
        """Get a source."""
        response = super().retrieve(request=request, args=args, kwargs=kwargs)

        return response

    @action(detail=True, methods=['get'])
    def status(self, request, *args, **kwargs):
        """Get source availability status."""
        source_id = kwargs.get('source_id')
        source_status_obj = SourceStatus(source_id)
        availability_status = source_status_obj.status()

        return Response(availability_status, status=status.HTTP_200_OK)
