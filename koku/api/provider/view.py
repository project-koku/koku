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
from rest_framework import mixins, viewsets
from rest_framework.authentication import (SessionAuthentication,
                                           TokenAuthentication)
from rest_framework.permissions import IsAuthenticated


from api.provider import serializers
from api.provider.models import Provider


class ProviderViewSet(mixins.CreateModelMixin,
                      viewsets.GenericViewSet):
    """Provider View .

    A viewset that provides default `create()` action.
    """

    lookup_field = 'uuid'
    queryset = Provider.objects.all()
    serializer_class = serializers.ProviderSerializer
    authentication_classes = (TokenAuthentication,
                              SessionAuthentication)
    permission_classes = (IsAuthenticated,)

    def create(self, request, *args, **kwargs):
        """Create a Provider.

        @api {post} /api/v1/providers/ Create a provider
        @apiName createProvider
        @apiGroup Provider
        @apiVersion 1.0.0
        @apiDescription Create a provider.

        @apiHeader {String} token User authorizaton token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorizaton": "Token 45138a913da44ab89532bab0352ef84b"
            }

        @apiParam (Request Body) {String} name The name for the provider.
        @apiParam (Request Body) {Object} authentication The authentication for the provider.
        @apiParam (Request Body) {Object} billing_source The billing source information for the provider.
        @apiParamExample {json} Request Body:
            {
            "name": "My Company AWS production",
            "authentication": {
                    'provider_resource_name': 'arn:aws:s3:::cost_s3'
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
                    "id": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                    "username": "smithj",
                    "email": "smithj@mytechco.com"
                }
            }
        """
        return super().create(request=request, args=args, kwargs=kwargs)
