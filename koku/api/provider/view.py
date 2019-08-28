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
from functools import reduce
from operator import and_

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.encoding import force_text
from django_filters import CharFilter, FilterSet
from django_filters.filters import BaseCSVFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.serializers import UUIDField

from api.iam.models import Customer
from api.provider import serializers
from api.provider.models import Provider
from api.report.view import get_tenant
from .provider_manager import ProviderManager


LOG = logging.getLogger(__name__)


class CharListFilter(BaseCSVFilter, CharFilter):
    """Add query filter capability to provide an anded list of filter values."""

    def filter(self, qs, value):
        """Filter to create a composite and filter of the value list."""
        if not value:
            return qs
        value_list = ','.join(value).split(',')
        queries = [Q(**{self.lookup_expr: val}) for val in value_list]
        return qs.filter(reduce(and_, queries))


class ProviderFilter(FilterSet):
    """Provider custom filters."""

    name = CharListFilter(field_name='name', lookup_expr='name__icontains')

    class Meta:
        model = Provider
        fields = ['type', 'name']


class ProviderDeleteException(APIException):
    """Provider deletion custom internal error exception."""

    default_detail = 'Error removing provider'

    def __init__(self):
        """Initialize with status code 500."""
        super().__init__()
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        self.detail = {'detail': force_text(self.default_detail)}


class ProviderViewSet(mixins.CreateModelMixin,
                      mixins.DestroyModelMixin,
                      mixins.ListModelMixin,
                      mixins.RetrieveModelMixin,
                      viewsets.GenericViewSet):
    """Provider View.

    A viewset that provides default `create()`, `retrieve()`,
    and `list()` actions.
    """

    lookup_field = 'uuid'
    queryset = Provider.objects.all()
    permission_classes = (AllowAny,)
    filter_backends = (DjangoFilterBackend,)
    filterset_class = ProviderFilter

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

        @api {post} /cost-management/v1/providers/ Create a provider
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
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 201 CREATED
            {
                "uuid": "9002b1db-0bf9-48bb-bd2a-9dc0c8e2742a",
                "name": "My Company Azure staging",
                "authentication": {
                        "uuid": "00dde2ed-91cc-401e-89ca-1d5e848ae3a6",
                        'credentials': {
                            'subscription_id': 'f695f74f-36a4-4112-9fe6-74415fac75a2',
                            'tenant_id': '319d4d72-7ddc-45d0-9d63-a2db0a36e048',
                            'client_id': 'ce26bd50-2e5a-4eb7-9504-a05a79568e25',
                            'client_secret': 'abc123'
                        }
                    },
                "billing_source": {
                        "uuid": "7347c1af-220c-4148-b52b-65e314f24999",
                        "data_source": { 'resource_group': 'My Resource Group 1',
                                         'storage_account': 'My Storage Account 2'
                        }
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

        @api {get} /cost-management/v1/providers/ Obtain the list of providers
        @apiName GetProviders
        @apiGroup Provider
        @apiVersion 1.0.0
        @apiDescription Obtain the list of providers.

        @apiHeader {String} token User authorization token.

        @apiParam (Query) {Number} page Parameter for selecting the page of data (default is 1)
        @apiParam (Query) {Number} page_size Parameter for selecting the amount of data in a page (default is 10)

        @apiSuccess {Object} meta The metadata for pagination.
        @apiSuccess {Object} links  The object containing links of results.
        @apiSuccess {Object[]} data  The array of results.
        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "meta": {
                    "count": 1
                }
                "links": {
                    "first": "/cost-management/v1/providers/?page=1",
                    "next": None,
                    "previous": None,
                    "last": "/cost-management/v1/providers/?page=1"
                },
                "data": [
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
                        },
                        "stats": {
                            "2019-01-01": [
                                {
                                    "assembly_id": "f0d262ff-cc93-449c-a834-74c4d958d45f",
                                    "billing_period_start": "2019-01-01",
                                    "files_processed": "1/1",
                                    "last_process_start_date": "2019-01-07 21:50:58",
                                    "last_process_complete_date": "2019-01-07 21:51:01",
                                    "summary_data_creation_datetime": "2019-01-07 21:51:32",
                                    "summary_data_updated_datetime": "2019-01-07 21:51:32"
                                }
                            ]
                        }
                        "infrastructure": "Unknown"
                    }
              ]
            }
        """
        response = super().list(request=request, args=args, kwargs=kwargs)
        for provider in response.data['data']:
            manager = ProviderManager(provider['uuid'])
            tenant = get_tenant(request.user)
            provider['stats'] = manager.provider_statistics(tenant)
            provider['infrastructure'] = manager.get_infrastructure_name(tenant)
        return response

    def retrieve(self, request, *args, **kwargs):
        """Get a provider.

        @api {get} /cost-management/v1/providers/:uuid/ Get a provider
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
        @apiSuccess {Object} stats  Report processing statistics.

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
                },
                "stats": {
                    "2019-01-01": [
                        {
                            "assembly_id": "f0d262ff-cc93-449c-a834-74c4d958d45f",
                            "billing_period_start": "2019-01-01",
                            "files_processed": "1/1",
                            "last_process_start_date": "2019-01-07 21:50:58",
                            "last_process_complete_date": "2019-01-07 21:51:01",
                            "summary_data_creation_datetime": "2019-01-07 21:51:32",
                            "summary_data_updated_datetime": "2019-01-07 21:51:32"
                        }
                    ]
                },
                "infrastructure": "Unknown"
            }
        """
        response = super().retrieve(request=request, args=args, kwargs=kwargs)
        tenant = get_tenant(request.user)
        manager = ProviderManager(kwargs['uuid'])
        response.data['infrastructure'] = manager.get_infrastructure_name(tenant)
        response.data['stats'] = manager.provider_statistics(tenant)
        return response

    def destroy(self, request, *args, **kwargs):
        """Delete a provider.

        @api {delete} /cost-management/v1/providers/:uuid/ Delete a provider
        @apiName DeleteProvider
        @apiGroup Provider
        @apiVersion 1.0.0
        @apiDescription Delete a provider.

        @apiHeader {String} token Authorization token of an authenticated user

        @apiParam {String} uuid Provider unique ID.

        @apiSuccessExample {json} Success-Response:
            HTTP/1.1 204 NO CONTENT
        """
        # throws ValidationError if pk is not a valid UUID
        uuid = UUIDField().to_internal_value(data=kwargs.get('uuid'))
        get_object_or_404(Provider, uuid=uuid)

        # Block any users not part of the organization
        if not self.get_queryset():
            raise PermissionDenied()
        manager = ProviderManager(uuid)
        try:
            manager.remove(request.user)
        except Exception:
            LOG.error('{} failed to remove provider uuid: {}.'.format(request.user, uuid))
            raise ProviderDeleteException

        return Response(status=status.HTTP_204_NO_CONTENT)
