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
import logging

from django.db import DatabaseError, transaction
from django.utils.encoding import force_text
from rest_framework import mixins, status, viewsets
from rest_framework.authentication import (SessionAuthentication,
                                           TokenAuthentication)
from rest_framework.exceptions import APIException, NotFound
from rest_framework.permissions import IsAdminUser

from api.iam import models
from api.iam import serializers
from api.iam.customer_manager import CustomerManager, CustomerManagerDoesNotExist, CustomerManagerValidationError
from api.provider.provider_manager import ProviderManager, ProviderManagerError
from api.provider.view import ProviderDeleteException

LOG = logging.getLogger(__name__)


class UserDeleteException(APIException):
    """User deletion custom internal error exception."""

    default_detail = 'Error removing user'

    def __init__(self):
        """Initialize with status code 500."""
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        self.detail = {'detail': force_text(self.default_detail)}


class CustomerViewSet(mixins.CreateModelMixin,
                      mixins.DestroyModelMixin,
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

        @apiHeader {String} token Service Admin authorization token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
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

        @apiSuccess {String} uuid The identifier of the customer.
        @apiSuccess {String} name  The name of the customer.
        @apiSuccess {Object} owner  The user associated with the customer creation.
        @apiSuccess {String} date_created  The date-time the customer is created.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 201 CREATED
            {
                "uuid": "600562e7-d7d7-4516-8522-410e72792daf",
                "name": "My Tech Company",
                "owner": {
                    "uuid": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
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

        @apiHeader {String} token Service Admin authorization token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
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
                        "uuid": "600562e7-d7d7-4516-8522-410e72792daf",
                        "name": "My Tech Company",
                        "owner": {
                            "uuid": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
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

        @api {get} /api/v1/customers/:uuid/ Get a customer
        @apiName GetCustomer
        @apiGroup Customer
        @apiVersion 1.0.0
        @apiDescription Get a customer.

        @apiHeader {String} token Service Admin authorization token.
        @apiHeaderExample {json} Header-Example:
            {
                "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
            }

        @apiParam {String} uuid Customer unique ID.

        @apiSuccess {String} uuid The identifier of the customer.
        @apiSuccess {String} name  The name of the customer.
        @apiSuccess {Object} owner  The user associated with the customer creation.
        @apiSuccess {String} date_created  The date-time the customer is created.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "uuid": "600562e7-d7d7-4516-8522-410e72792daf",
                "name": "My Tech Company",
                "owner": {
                    "uuid": "57e60f90-8c0c-4bd1-87a0-2143759aae1c",
                    "username": "smithj",
                    "email": "smithj@mytechco.com"
                },
                "date_created": "2018-05-09T18:17:29.386Z"
            }
        """
        return super().retrieve(request=request, args=args, kwargs=kwargs)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
            """Delete a customer.

            @api {delete} /api/v1/customers/:uuid/ Delete a customer
            @apiName DeleteCustomers
            @apiGroup Customer
            @apiVersion 1.0.0
            @apiDescription Delete a customer.

            @apiHeader {String} token Service Admin authorization token.
            @apiHeaderExample {json} Header-Example:
                {
                    "Authorization": "Token 45138a913da44ab89532bab0352ef84b"
                }

            @apiParam {String} uuid Customer unique ID.

            @apiSuccessExample {json} Success-Response:
                HTTP/1.1 204 NO CONTENT
            """
            user_savepoint = transaction.savepoint()
            customer_manager = None
            try:
                customer_manager = CustomerManager(kwargs['uuid'])
            except (CustomerManagerDoesNotExist, CustomerManagerValidationError):
                LOG.error('Unable to find provider for uuid {}.'.format(kwargs['uuid']))
                raise NotFound

            providers = ProviderManager.get_providers_queryset_for_customer(customer_manager.get_model())

            try:
                customer_manager.remove_users(request.user)
                customer_manager.remove_tenant(request.user)
            except DatabaseError:
                transaction.savepoint_rollback(user_savepoint)
                LOG.error('Failed to remove assets for customer {}.'.format(customer_manager.get_name()))
                raise UserDeleteException

            try:
                for provider in providers:
                    provider_manager = ProviderManager(provider.uuid)
                    provider_manager.remove(request.user, customer_remove_context=True)
            except (DatabaseError, ProviderManagerError):
                transaction.savepoint_rollback(user_savepoint)
                LOG.error('{} failed to remove provider {}.'.format(request.user.username, provider_manager.get_name()))
                raise ProviderDeleteException

            http_response = super().destroy(request=request, args=args, kwargs=kwargs)
            if http_response.status_code is not 204:
                transaction.savepoint_rollback(user_savepoint)
            return http_response
