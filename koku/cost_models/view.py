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

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.encoding import force_text
from django_filters import CharFilter, FilterSet
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
            'uuid',
        ]


class RateProviderPermissionDenied(APIException):
    """Rate query custom internal error exception."""

    default_detail = 'You do not have permission to perform this action.'

    def __init__(self):
        """Initialize with status code 500."""
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

    # def get_queryset(self):  # noqa: C901
    #     """Get a queryset.

    #     Restricts the returned data to provider_uuid if supplied as a query parameter.
    #     """
    #     queryset = CostModel.objects.all()
    #     provider_uuid = self.request.query_params.get('provider_uuid')
    #     if provider_uuid:
    #         cost_model_uuids = []
    #         for e in CostModelMap.objects.filter(provider_uuid=provider_uuid):
    #             cost_model_uuids.append(e.cost_model.uuid)
    #         queryset = CostModel.objects.filter(uuid__in=cost_model_uuids)
    #     if not self.request.user.admin:
    #         read_access_list = self.request.user.access.get('rate').get('read')
    #         if '*' not in read_access_list:
    #             for access_item in read_access_list:
    #                 try:
    #                     UUID(access_item)
    #                 except ValueError:
    #                     err_msg = 'Unexpected rbac access item.  {} is not a uuid.'.format(access_item)
    #                     raise CostModelProviderQueryException(err_msg)
    #             try:
    #                 queryset = self.queryset.filter(uuid__in=read_access_list)
    #             except ValidationError as queryset_error:
    #                 LOG.error(queryset_error)
    #     return queryset

    def create(self, request, *args, **kwargs):
        """Create a rate.

        @api {post} /cost-management/v1/rates/   Create a rate
        @apiName createRate
        @apiGroup Rates
        @apiVersion 1.0.0
        @apiDescription Create a Rate

        @apiHeader {String} token User authorization token

        @apiParam (Request Body) {String} name Rate name
        @apiParam (Request Body) {String} description Rate description
        @apiParam (Request Body) {String} price Rate price
        @apiParam (Request Body) {String} metric Metric
        @apiParam (Request Body) {String} timeunit Unit of time
        @apiParamExample {json} Request Body:
            {
                "provider_uuid": "a1de6812-0c26-4b33-acdb-3bad8b1ef295",
                "metric": "cpu_core_usage_per_hour",
                "tiered_rate": [{
                    "value": 0.022,
                    "unit": "USD",
                    "usage_start": null,
                    "usage_end": null,
                }]
            }

        @apiSuccess {String} uuid Rate unique identifier
        @apiSuccess {String} name Rate name
        @apiSuccess {String} description Rate description
        @apiSuccess {String} price Rate price
        @apiSuccess {String} metric Metric
        @apiSuccess {String} timeunit Unit of time
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 201 CREATED
            {
                "uuid": "16fd2706-8baf-433b-82eb-8c7fada847da",
                "provider_uuid": "a1de6812-0c26-4b33-acdb-3bad8b1ef295",
                "metric": "cpu_core_usage_per_hour",
                "tiered_rate": [{
                    "value": 0.022,
                    "unit": "USD",
                    "usage_start": null,
                    "usage_end": null,
                }]
            }
        """
        return super().create(request=request, args=args, kwargs=kwargs)

    def list(self, request, *args, **kwargs):
        """Obtain the list of rates for the tenant.

        @api {get} /cost-management/v1/rates/   Obtain a list of rates
        @apiName getRates
        @apiGroup Rates
        @apiVersion 1.0.0
        @apiDescription Obtain a list of rates

        @apiHeader {String} token User authorization token

        @apiParam (Query) {Number} page Parameter for selecting the page of data (default is 1).
        @apiParam (Query) {Number} page_size Parameter for selecting the amount of data in a page (default is 10).

        @apiSuccess {Object} meta The metadata for pagination.
        @apiSuccess {Object} links  The object containing links of results.
        @apiSuccess {Object[]} data  The array of results.

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                'meta': {
                    'count': 2
                }
                'links': {
                    'first': /cost-management/v1/rates/?page=1,
                    'next': None,
                    'previous': None,
                    'last': /cost-management/v1/rates/?page=1
                },
                'data': [
                    {
                        "uuid": "16fd2706-8baf-433b-82eb-8c7fada847da",
                        "provider_uuid": "a1de6812-0c26-4b33-acdb-3bad8b1ef295",
                        "metric": {
                            "name": "cpu_core_usage_per_hour",
                            "unit": "core-hours",
                            "display_name": "Compute usage rate"
                        }
                        "tiered_rate": [{
                            "value": 0.022,
                            "unit": "USD",
                            "usage": {
                                "usage_start": null,
                                "usage_end": null,
                                "unit": "cpu-hours"
                            }
                        }]
                    },
                    {
                        "uuid": "20ecdcd0-397c-4ede-8940-f3439bf40212",
                        "provider_uuid": "a1de6812-0c26-4b33-acdb-3bad8b1ef295",
                        "metric": "memory_gb_usage_per_hour",
                        "tiered_rate": [{
                            "value": 0.022,
                            "unit": "USD",
                            "usage": {
                                "usage_start": null,
                                "usage_end": null,
                                "unit": "GB-hours"
                            }
                        }]
                    }
                ]
            }

        """
        try:
            response = super().list(request=request, args=args, kwargs=kwargs)
        except ValidationError:
            raise CostModelProviderQueryException('Invalid provider uuid')

        return response

    def retrieve(self, request, *args, **kwargs):
        """Get a rate.

        @api {get} /cost-management/v1/rates/:uuid   Get a rate
        @apiName getRate
        @apiGroup Rates
        @apiVersion 1.0.0
        @apiDescription Get a rate

        @apiHeader {String} token User authorization token

        @apiParam (Query) {String} id Rate unique identifier.

        @apiSuccess {String} uuid Rate unique identifier
        @apiSuccess {String} name Rate name
        @apiSuccess {String} description Rate description
        @apiSuccess {String} price Rate price
        @apiSuccess {String} metric Metric
        @apiSuccess {String} timeunit Unit of time
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "uuid": "16fd2706-8baf-433b-82eb-8c7fada847da",
                "provider_uuid": "a1de6812-0c26-4b33-acdb-3bad8b1ef295",
                "metric": {
                    "name": "cpu_core_usage_per_hour",
                    "unit": "core-hours",
                    "display_name": "Compute usage rate"
                }
                "tiered_rate": [{
                    "value": 0.022,
                    "unit": "USD",
                    "usage_start": null,
                    "usage_end": null,
                }]
            }
        """
        return super().retrieve(request=request, args=args, kwargs=kwargs)

    def destroy(self, request, *args, **kwargs):
        """Delete a rate.

        @api {delete} /cost-management/v1/rates/:uuid   Get a rate
        @apiName deleteRate
        @apiGroup Rates
        @apiVersion 1.0.0
        @apiDescription Delete a rate

        @apiHeader {String} token User authorization token

        @apiParam (Query) {String} uuid Rate unique identifier

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 204 NO CONTENT
        """
        return super().destroy(request=request, args=args, kwargs=kwargs)

    def update(self, request, *args, **kwargs):
        """Update a rate.

        @api {post} /cost-management/v1/rates/:uuid   Update a rate
        @apiName updateRate
        @apiGroup Rates
        @apiVersion 1.0.0
        @apiDescription Update a Rate

        @apiHeader {String} token User authorization token

        @apiParam (Query) {String} id Rate unique identifier

        @apiSuccess {String} uuid Rate unique identifier
        @apiSuccess {String} name Rate name
        @apiSuccess {String} description Rate description
        @apiSuccess {String} price Rate price
        @apiSuccess {String} metric Metric
        @apiSuccess {String} timeunit Unit of time
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "uuid": "16fd2706-8baf-433b-82eb-8c7fada847da",
                "provider_uuid": "a1de6812-0c26-4b33-acdb-3bad8b1ef295",
                "metric": "cpu_core_usage_per_hour",
                "tiered_rate": [{
                    "value": 0.022,
                    "unit": "USD",
                    "usage_start": null,
                    "usage_end": null,
                }]
            }
        """
        if request.method == 'PATCH':
            raise CostModelProviderMethodException('PATCH not supported')
        return super().update(request=request, args=args, kwargs=kwargs)
