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

"""View for Customers."""

from rest_framework import mixins, viewsets
from rest_framework.authentication import (SessionAuthentication,
                                           TokenAuthentication)
from rest_framework.permissions import IsAdminUser

from api.iam import models
from  api.iam import serializers


class CustomerViewSet(mixins.CreateModelMixin,
                      mixins.ListModelMixin,
                      mixins.RetrieveModelMixin,
                      viewsets.GenericViewSet):
    """Customer View.

    A viewset that provides default `create()`, `retrieve()`,
    and `list()` actions.
    """

    lookup_field = 'uuid'
    queryset = models.Customer.objects.all()
    serializer_class = serializers.CustomerSerializer
    authentication_classes = (TokenAuthentication,
                              SessionAuthentication)
    permission_classes = (IsAdminUser,)

    def perform_create(self, serializer):
        """Create a customer with a tenant."""
        customer = serializer.save()
        tenant = models.Tenant(schema_name=customer.schema_name)
        tenant.save()

    def create(self, request, *args, **kwargs):
        """Create a customer.

        @api {post} /api/v1/customers/ Create a customer
        @apiName createCustomer
        @apiGroup Customer
        @apiVersion 1.0.0
        @apiDescription Create a customer.

        @apiHeader {String} token Service Admin authorizaton token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorizaton": "Token 45138a913da44ab89532bab0352ef84b"
            }

        @apiParam (Request Body) {String} name Customer Name
        @apiParam (Request Body) {Object} owner User object
        @apiParamExample {json} Request Body:
            {
            "name": "My Tech Company",
            "owner": {
                "username": "smithj",
                "email": "smithj@mytechco.com",
                "password": "str0ng!P@ss"
                }
            }

        @apiSuccess {Number} id The identifier of the customer.
        @apiSuccess {String} name  The name of the customer.
        @apiSuccess {Object} owner  The user associated with the customer creation.
        @apiSuccess {String} date_created  The date-time the customer is created.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 201 CREATED
            {
                "id": "600562e7-d7d7-4516-8522-410e72792daf",
                "name": "My Tech Company",
                "owner": {
                    "id": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                    "username": "smithj",
                    "email": "smithj@mytechco.com"
                },
                "date_created": "2018-05-09T18:17:29.386Z"
            }
        """
        return super().create(request=request, args=args, kwargs=kwargs)

    def list(self, request, *args, **kwargs):
        """Obtain the list of customers.

        @api {get} /api/v1/customers/ Obtain the list of customers
        @apiName GetCustomers
        @apiGroup Customer
        @apiVersion 1.0.0
        @apiDescription Obtain the list of customers.

        @apiHeader {String} token Service Admin authorizaton token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorizaton": "Token 45138a913da44ab89532bab0352ef84b"
            }

        @apiSuccess {Number} count The number of customers.
        @apiSuccess {String} previous  The uri of the previous page of results.
        @apiSuccess {String} next  The uri of the previous page of results.
        @apiSuccess {Object[]} results  The array of customer results.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "count": 30,
                "previous": "/api/v1/customers/?page=2",
                "next": "/api/v1/customers/?page=4",
                "results": [
                    {
                        "id": "600562e7-d7d7-4516-8522-410e72792daf",
                        "name": "My Tech Company",
                        "owner": {
                            "id": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                            "username": "smithj",
                            "email": "smithj@mytechco.com"
                          },
                         "date_created": "2018-05-09T18:17:29.386Z"
                    }
              ]
            }
        """
        return super().list(request=request, args=args, kwargs=kwargs)

    def retrieve(self, request, *args, **kwargs):
        """Get a customer.

        @api {get} /api/v1/customers/:id/ Get a customer
        @apiName GetCustomer
        @apiGroup Customer
        @apiVersion 1.0.0
        @apiDescription Get a customer.

        @apiHeader {String} token Service Admin authorizaton token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorizaton": "Token 45138a913da44ab89532bab0352ef84b"
            }

        @apiParam {Number} id Customer unique ID.

        @apiSuccess {Number} id The identifier of the customer.
        @apiSuccess {String} name  The name of the customer.
        @apiSuccess {Object} owner  The user associated with the customer creation.
        @apiSuccess {String} date_created  The date-time the customer is created.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "id": "600562e7-d7d7-4516-8522-410e72792daf",
                "name": "My Tech Company",
                "owner": {
                    "id": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                    "username": "smithj",
                    "email": "smithj@mytechco.com"
                },
                "date_created": "2018-05-09T18:17:29.386Z"
            }
        """
        return super().retrieve(request=request, args=args, kwargs=kwargs)
