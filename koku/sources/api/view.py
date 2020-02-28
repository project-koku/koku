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
from django.shortcuts import get_object_or_404

"""View for Sources."""
import logging

from django.conf import settings
from django.utils.encoding import force_text
from django.views.decorators.cache import never_cache
from django_filters import FilterSet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions
from rest_framework import mixins
from rest_framework import status
from rest_framework import viewsets
from rest_framework.exceptions import APIException
from rest_framework.exceptions import ParseError
from rest_framework.permissions import AllowAny

from api.common.filters import CharListFilter
from api.provider.models import Sources
from sources.api import get_account_from_header, get_auth_header
from sources.api.serializers import SourcesSerializer
from sources.api.serializers import AdminSourcesSerializer
from sources.storage import SourcesStorageError
from sources.kafka_source_manager import KafkaSourceManager


LOG = logging.getLogger(__name__)
MIXIN_LIST = [mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet]


class DestroySourceMixin(mixins.DestroyModelMixin):
    """A mixin for destroying a source."""

    @never_cache
    def destroy(self, request, *args, **kwargs):
        """Delete a source."""
        account_id = get_account_from_header(request)
        source = get_object_or_404(Sources, source_id=kwargs.get("source_id"), account_id=account_id)
        manager = KafkaSourceManager(get_auth_header(request))
        manager.destroy_provider(source.koku_uuid)
        response = super().destroy(request, *args, **kwargs)
        return response


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

    lookup_field = "source_id"
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
        if self.request.method in permissions.SAFE_METHODS:
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
        return super().list(request=request, args=args, kwargs=kwargs)

    @never_cache
    def retrieve(self, request, *args, **kwargs):
        """Get a source."""
        response = super().retrieve(request=request, args=args, kwargs=kwargs)

        return response
