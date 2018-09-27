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

from django.utils.encoding import force_text
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api.iam.models import Customer
from api.provider import serializers
from api.provider.models import Provider
from .provider_manager import ProviderManager


LOG = logging.getLogger(__name__)


class ProviderDeleteException(APIException):
    """Provider deletion custom internal error exception."""

    default_detail = 'Error removing provider'

    def __init__(self):
        """Initialize with status code 500."""
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        self.detail = {'detail': force_text(self.default_detail)}


class ProviderViewSet(mixins.CreateModelMixin,
                      mixins.DestroyModelMixin,
                      mixins.ListModelMixin,
                      mixins.RetrieveModelMixin,
                      viewsets.GenericViewSet):
    """Provider View .

    A viewset that provides default `create()`, `retrieve()`,
    and `list()` actions.
    """

    lookup_field = 'uuid'
    queryset = Provider.objects.all()
    permission_classes = (AllowAny,)

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
        """Create a Provider.

        @api {post} /api/v1/providers/ Create a provider
        @apiName createProvider
        @apiGroup Provider
        @apiVersion 1.0.0
        @apiDescription Create a provider.

        @apiHeader {String} token User authorization token.

        @apiParam (Request Body) {String} name The name for the provider.
        @apiParam (Request Body) {String} type The provider type.
        @apiParam (Request Body) {Object} authentication The authentication for the provider.
        @apiParam (Request Body) {Object} billing_source The billing source information for the provider.
        @apiParamExample {json} Request Body:
            {
            "name": "My Company AWS production",
            "type": "AWS",
            "authentication": {
                    'provider_resource_name': 'arn:aws:iam::PRODUCTION-ACCOUNT-ID:role/CostData'
                },
            "billing_source": {
                    "bucket": "cost_s3"
                }
            }

        @apiSuccess {String} uuid The identifier of the provider.
        @apiSuccess {String} name  The name of the provider.
        @apiSuccess {Object} authentication  The authentication for the provider.
        @apiSuccess {Object} billing_source  The billing source information for the provider.
        @apiSuccess {Object} customer  The customer the provider is assocaited with.
        @apiSuccess {Object} created_by  The user the provider was created by.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 201 CREATED
            {
                "uuid": "9002b1db-0bf9-48bb-bd2a-9dc0c8e2742a",
                "name": "My Company AWS production",
                "authentication": {
                        "uuid": "00dde2ed-91cc-401e-89ca-1d5e848ae3a6",
                        'provider_resource_name': 'arn:aws:s3:::cost_s3'
                    },
                "billing_source": {
                        "uuid": "7347c1af-220c-4148-b52b-65e314f24999",
                        "bucket": "cost_s3"
                    },
                "customer": {
                    "uuid": "600562e7-d7d7-4516-8522-410e72792daf",
                    "name": "My Tech Company",
                    "owner": {
                        "uuid": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                        "username": "smithj",
                        "email": "smithj@mytechco.com"
                    },
                    "date_created": "2018-05-09T18:17:29.386Z"
                },
                "created_by": {
                    "uuid": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                    "username": "smithj",
                    "email": "smithj@mytechco.com"
                }
            }
        """
        return super().create(request=request, args=args, kwargs=kwargs)

    def list(self, request, *args, **kwargs):
        """Obtain the list of providers.

        @api {get} /api/v1/providers/ Obtain the list of providers
        @apiName GetProviders
        @apiGroup Provider
        @apiVersion 1.0.0
        @apiDescription Obtain the list of providers.

        @apiHeader {String} token User authorization token.

        @apiSuccess {Number} count The number of users.
        @apiSuccess {String} previous  The uri of the previous page of results.
        @apiSuccess {String} next  The uri of the previous page of results.
        @apiSuccess {Object[]} results  The array of provider results.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "count": 30,
                "previous": "/api/v1/providers/?page=2",
                "next": "/api/v1/providers/?page=4",
                "results": [
                    {
                        "uuid": "9002b1db-0bf9-48bb-bd2a-9dc0c8e2742a",
                        "name": "My Company AWS production",
                        "authentication": {
                                "uuid": "00dde2ed-91cc-401e-89ca-1d5e848ae3a6",
                                'provider_resource_name': 'arn:aws:s3:::cost_s3'
                            },
                        "billing_source": {
                                "uuid": "7347c1af-220c-4148-b52b-65e314f24999",
                                "bucket": "cost_s3"
                            },
                        "customer": {
                            "uuid": "600562e7-d7d7-4516-8522-410e72792daf",
                            "name": "My Tech Company",
                            "owner": {
                                "uuid": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                                "username": "smithj",
                                "email": "smithj@mytechco.com"
                            },
                            "date_created": "2018-05-09T18:17:29.386Z"
                        },
                        "created_by": {
                            "uuid": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                            "username": "smithj",
                            "email": "smithj@mytechco.com"
                        }
                    }
              ]
            }
        """
        return super().list(request=request, args=args, kwargs=kwargs)

    def retrieve(self, request, *args, **kwargs):
        """Get a provider.

        @api {get} /api/v1/providers/:uuid/ Get a provider
        @apiName GetProvider
        @apiGroup Provider
        @apiVersion 1.0.0
        @apiDescription Get a provider.

        @apiHeader {String} token User authorization token.

        @apiParam {String} uuid Provider unique ID.

        @apiSuccess {String} uuid The identifier of the provider.
        @apiSuccess {String} name  The name of the provider.
        @apiSuccess {Object} authentication  The authentication for the provider.
        @apiSuccess {Object} billing_source  The billing source information for the provider.
        @apiSuccess {Object} customer  The customer the provider is assocaited with.
        @apiSuccess {Object} created_by  The user the provider was created by.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "uuid": "9002b1db-0bf9-48bb-bd2a-9dc0c8e2742a",
                "name": "My Company AWS production",
                "authentication": {
                        "uuid": "00dde2ed-91cc-401e-89ca-1d5e848ae3a6",
                        'provider_resource_name': 'arn:aws:s3:::cost_s3'
                    },
                "billing_source": {
                        "uuid": "7347c1af-220c-4148-b52b-65e314f24999",
                        "bucket": "cost_s3"
                    },
                "customer": {
                    "uuid": "600562e7-d7d7-4516-8522-410e72792daf",
                    "name": "My Tech Company",
                    "owner": {
                        "uuid": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                        "username": "smithj",
                        "email": "smithj@mytechco.com"
                    },
                    "date_created": "2018-05-09T18:17:29.386Z"
                },
                "created_by": {
                    "uuid": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                    "username": "smithj",
                    "email": "smithj@mytechco.com"
                }
            }
        """
        return super().retrieve(request=request, args=args, kwargs=kwargs)

    def destroy(self, request, *args, **kwargs):
            """Delete a provider.

            @api {delete} /api/v1/providers/:uuid/ Delete a provider
            @apiName DeleteProvider
            @apiGroup Provider
            @apiVersion 1.0.0
            @apiDescription Delete a provider.

            @apiHeader {String} token Authorization token of an authenticated user

            @apiParam {String} uuid Provider unique ID.

            @apiSuccessExample {json} Success-Response:
                HTTP/1.1 204 NO CONTENT
            """
            # Block any users not part of the organization
            if not self.get_queryset():
                raise PermissionDenied()

            manager = ProviderManager(kwargs['uuid'])
            try:
                manager.remove(request.user)
            except Exception:
                LOG.error('{} failed to remove provider uuid: {}.'.format(request.user, kwargs['uuid']))
                raise ProviderDeleteException

            return Response(status=status.HTTP_204_NO_CONTENT)
