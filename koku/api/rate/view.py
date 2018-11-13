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
from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny

from api.rate.serializers import RateSerializer
from reporting.rate.models import Rate


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

    def create(self, request, *args, **kwargs):
        """Create a rate.

        @api {post} /api/v1/rates/   Create a rate
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
                "name": "My Rate",
                "description": "This is an example rate.",
                "price": "0.001",
                "metric": "cpu_ticks",
                "timeunit": "hour"
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
                "name": "My Rate",
                "description": "This is an example rate.",
                "price": "0.001",
                "metric": "cpu_ticks",
                "timeunit": "hour"
            }
        """
        return super().create(request=request, args=args, kwargs=kwargs)

    def list(self, request, *args, **kwargs):
        """Obtain the list of rates for the tenant.

        @api {get} /api/v1/rates/   Obtain a list of rates
        @apiName getRates
        @apiGroup Rates
        @apiVersion 1.0.0
        @apiDescription Obtain a list of rates

        @apiHeader {String} token User authorization token

        @apiParam (Query) {String} name Filter by rate name.

        @apiSuccess {Number} count The number of rates.
        @apiSuccess {String} previous  The uri of the previous page of results.
        @apiSuccess {String} next  The uri of the next page of results.
        @apiSuccess {Object[]} results  The array of rate results.

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                'count': 2,
                'next': None,
                'previous': None,
                'results': [
                                {
                                    "uuid": "16fd2706-8baf-433b-82eb-8c7fada847da",
                                    "name": "My Rate",
                                    "description": "This is an example rate.",
                                    "price": "0.001",
                                    "metric": "cpu_ticks",
                                    "timeunit": "hour"
                                },
                                {
                                    "uuid": "20ecdcd0-397c-4ede-8940-f3439bf40212",
                                    "name": "My Other Rate",
                                    "description": "This is another example rate.",
                                    "price": "0.002",
                                    "metric": "memory_bytes_hours",
                                    "timeunit": "nil"
                                }
                            ]
            }

        """
        return super().list(request=request, args=args, kwargs=kwargs)

    def retrieve(self, request, *args, **kwargs):
        """Get a rate.

        @api {get} /api/v1/rates/:uuid   Get a rate
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
                "name": "My Rate",
                "description": "This is an example rate.",
                "price": "0.001",
                "metric": "cpu_ticks",
                "timeunit": "hour"
            }
        """
        return super().retrieve(request=request, args=args, kwargs=kwargs)

    def destroy(self, request, *args, **kwargs):
        """Delete a rate.

        @api {delete} /api/v1/rates/:uuid   Get a rate
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

        @api {post} /api/v1/rates/:uuid   Update a rate
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
                "name": "My Rate",
                "description": "This is an example rate.",
                "price": "0.001",
                "metric": "cpu_ticks",
                "timeunit": "hour"
            }
        """
        return super().update(request=request, args=args, kwargs=kwargs)
