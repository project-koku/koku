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

"""View for Rates."""
import logging
from functools import reduce
from operator import and_
from uuid import UUID

from django.core.exceptions import FieldError, ValidationError
from django.db.models import Q
from django.utils.encoding import force_text
from django_filters import CharFilter, FilterSet, ModelChoiceFilter, UUIDFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import APIException

from api.common.permissions.cost_models_access import CostModelsAccessPermission
from cost_models.models import CostModel, CostModelMap
from cost_models.serializers import CostModelSerializer

LOG = logging.getLogger(__name__)


class CostModelsFilter(FilterSet):
    """Cost model custom filters."""

    name = CharFilter(field_name='name', method='list_contain_filter')
    uuid = UUIDFilter(field_name='uuid')
    provider_uuid = ModelChoiceFilter(queryset=CostModelMap.objects.all())

    def list_contain_filter(self, qs, name, values):
        """Filter items that contain values in their name."""
        lookup = '__'.join([name, 'icontains'])
        value_list = ','.join(values).split(',')
        queries = [Q(**{lookup: val}) for val in value_list]
        return qs.filter(reduce(and_, queries))

    class Meta:
        model = CostModel
        fields = [
            'source_type',
            'name',
            'provider_uuid'
        ]


class RateProviderPermissionDenied(APIException):
    """Rate query custom internal error exception."""

    default_detail = 'You do not have permission to perform this action.'

    def __init__(self):
        """Initialize with status code 403."""
        self.status_code = status.HTTP_403_FORBIDDEN
        self.detail = {'detail': force_text(self.default_detail)}


class CostModelProviderQueryException(APIException):
    """Rate query custom internal error exception."""

    def __init__(self, message):
        """Initialize with status code 500."""
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        self.detail = {'detail': force_text(message)}


class CostModelProviderMethodException(APIException):
    """General Exception class for ProviderManager errors."""

    def __init__(self, message):
        """Set custom error message for ProviderManager errors."""
        self.status_code = status.HTTP_405_METHOD_NOT_ALLOWED
        self.detail = {'detail': force_text(message)}


class CostModelViewSet(mixins.CreateModelMixin,
                       mixins.DestroyModelMixin,
                       mixins.ListModelMixin,
                       mixins.RetrieveModelMixin,
                       mixins.UpdateModelMixin,
                       viewsets.GenericViewSet):
    """CostModel View.

    A viewset that provides default `create()`, `destroy`, `retrieve()`,
    and `list()` actions.

    """

    queryset = CostModel.objects.all()
    serializer_class = CostModelSerializer
    permission_classes = (CostModelsAccessPermission,)
    lookup_field = 'uuid'
    filter_backends = (DjangoFilterBackend,)
    filterset_class = CostModelsFilter

    @staticmethod
    def check_fields(model, dict_, exception):
        """Check if GET fields are valid."""
        try:
            model.objects.filter(**dict_)
        except FieldError as fe:
            raise exception(fe)


    def get_queryset(self):  # noqa: C901
        """Get a queryset.

        Restricts the returned data to provider_uuid if supplied as a query parameter.
        # """
        queryset = CostModel.objects.all()
        provider_uuid = self.request.query_params.get('provider_uuid')
        if not provider_uuid:
            self.check_fields(CostModel, self.request.query_params, CostModelProviderQueryException)

        if provider_uuid:
            dict_ = {k: self.request.query_params[k] for k in self.request.query_params.keys() if k != 'provider_uuid'}
            self.check_fields(CostModel, dict_, CostModelProviderQueryException)
        if not self.request.user.admin:
            read_access_list = self.request.user.access.get('rate').get('read')
            if '*' not in read_access_list:
                try:
                    queryset = self.queryset.filter(uuid__in=read_access_list)
                except ValidationError as queryset_error:
                    LOG.error(queryset_error)
        return queryset

    def create(self, request, *args, **kwargs):
        """Create a rate."""
        return super().create(request=request, args=args, kwargs=kwargs)

    def list(self, request, *args, **kwargs):
        """Obtain the list of rates for the tenant."""
        try:
            response = super().list(request=request, args=args, kwargs=kwargs)
        except ValidationError:
            raise CostModelProviderQueryException('Invalid provider uuid')

        return response

    def retrieve(self, request, *args, **kwargs):
        """Get a rate."""
        return super().retrieve(request=request, args=args, kwargs=kwargs)

    def destroy(self, request, *args, **kwargs):
        """Delete a rate."""
        return super().destroy(request=request, args=args, kwargs=kwargs)

    def update(self, request, *args, **kwargs):
        """Update a rate."""
        if request.method == 'PATCH':
            raise CostModelProviderMethodException('PATCH not supported')
        return super().update(request=request, args=args, kwargs=kwargs)
