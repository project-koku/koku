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

from django.core.exceptions import ValidationError
from django.utils.encoding import force_text
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny

from rates.models import Rate
from rates.serializers import RateSerializer


LOG = logging.getLogger(__name__)


class RateProviderQueryException(APIException):
    """Rate query custom internal error exception."""

    default_detail = 'Invalid provider uuid'

    def __init__(self):
        """Initialize with status code 500."""
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        self.detail = {'detail': force_text(self.default_detail)}


class RateViewSet(mixins.CreateModelMixin,
                  mixins.DestroyModelMixin,
                  mixins.ListModelMixin,
                  mixins.RetrieveModelMixin,
                  mixins.UpdateModelMixin,
                  viewsets.GenericViewSet):
    """Rate View.

    A viewset that provides default `create()`, `destroy`, `retrieve()`,
    and `list()` actions.

    """

    queryset = Rate.objects.all()
    serializer_class = RateSerializer
    permission_classes = (AllowAny,)
    lookup_field = 'uuid'

    def get_queryset(self):
        """Get a queryset.

        Restricts the returned data to provider_uuid if supplied as a query parameter.
        """
        queryset = Rate.objects.all()

        provider_uuid = self.request.query_params.get('provider_uuid')
        if provider_uuid:
            queryset = Rate.objects.filter(provider_uuid=provider_uuid)
        return queryset

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
            raise RateProviderQueryException

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
        return super().update(request=request, args=args, kwargs=kwargs)
