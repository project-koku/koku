#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Rates."""
import logging
from functools import reduce
from operator import and_

from django.conf import settings
from django.core.exceptions import FieldError
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.utils.encoding import force_str
from django.views.decorators.cache import never_cache
from django_filters import CharFilter
from django_filters import FilterSet
from django_filters import UUIDFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers
from rest_framework import status
from rest_framework import viewsets
from rest_framework.exceptions import APIException
from rest_framework.filters import OrderingFilter

from api.common.filters import CharListFilter
from api.common.permissions.cost_models_access import CostModelsAccessPermission
from api.currency.currencies import VALID_CURRENCIES
from cost_models.cost_model_manager import CostModelManager
from cost_models.models import CostModel
from cost_models.serializers import CostModelSerializer

LOG = logging.getLogger(__name__)


class CostModelsFilter(FilterSet):
    """Cost model custom filters."""

    name = CharFilter(field_name="name", method="list_contain_filter")
    uuid = UUIDFilter(field_name="uuid")
    source_uuid = UUIDFilter(field_name="costmodelmap__provider_uuid")
    description = CharFilter(field_name="description", method="list_contain_filter")
    source_type = CharListFilter(field_name="source_type", lookup_expr="source_type__iexact")
    currency = CharListFilter(field_name="currency", method="currency_filter")

    def currency_filter(self, qs, name, values):
        """Filter currency if a valid currency is passed in"""
        if values and values[0].upper() not in VALID_CURRENCIES:
            error = {"currency": f'"{values[0]}" is not a valid choice.'}
            raise serializers.ValidationError(error)
        lookup = "__".join([name, "iexact"])
        queries = [Q(**{lookup: val}) for val in values]
        return qs.filter(reduce(and_, queries))

    def list_contain_filter(self, qs, name, values):
        """Filter items that contain values in their name."""
        lookup = "__".join([name, "icontains"])
        value_list = values.split(",")
        queries = [Q(**{lookup: val}) for val in value_list]
        return qs.filter(reduce(and_, queries))

    class Meta:
        model = CostModel
        fields = ["source_type", "name", "source_uuid", "description", "currency"]


class RateProviderPermissionDenied(APIException):
    """Rate query custom internal error exception."""

    default_detail = "You do not have permission to perform this action."

    def __init__(self):
        """Initialize with status code 403."""
        self.status_code = status.HTTP_403_FORBIDDEN
        self.detail = {"detail": force_str(self.default_detail)}


class CostModelQueryException(APIException):
    """Invalid query field exception."""

    def __init__(self, message):
        """Initialize with status code 400."""
        self.status_code = status.HTTP_400_BAD_REQUEST
        self.detail = {"detail": force_str(message)}


class CostModelProviderQueryException(APIException):
    """Rate query custom internal error exception."""

    def __init__(self, message):
        """Initialize with status code 500."""
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        self.detail = {"detail": force_str(message)}


class CostModelProviderMethodException(APIException):
    """General Exception class for ProviderManager errors."""

    def __init__(self, message):
        """Set custom error message for ProviderManager errors."""
        self.status_code = status.HTTP_405_METHOD_NOT_ALLOWED
        self.detail = {"detail": force_str(message)}


class CostModelViewSet(viewsets.ModelViewSet):
    """CostModel View.

    A viewset that provides default `create()`, `destroy`, `retrieve()`,
    and `list()` actions.

    """

    queryset = CostModel.objects.all()
    serializer_class = CostModelSerializer
    permission_classes = (CostModelsAccessPermission,)
    lookup_field = "uuid"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = CostModelsFilter
    ordering_fields = ("name", "source_type", "updated_timestamp")
    ordering = ("name",)
    http_method_names = ["get", "post", "head", "delete", "put"]

    @staticmethod
    def check_fields(dict_, model, exception):
        """Check if GET fields are valid."""
        valid_query_params = ["limit", "offset", "source_uuid", "ordering", "currency"]
        cost_models_params = {k: dict_.get(k) for k in dict_.keys() if k not in valid_query_params}
        try:
            model.objects.filter(**cost_models_params)
        except FieldError as fe:
            raise exception(fe)

    def get_queryset(self):
        """Get a queryset.

        Restricts the returned data to source_uuid if supplied as a query parameter.
        """
        queryset = CostModel.objects.all()
        self.check_fields(self.request.query_params, CostModel, CostModelQueryException)
        if not (settings.ENHANCED_ORG_ADMIN and self.request.user.admin):
            read_access_list = self.request.user.access.get("cost_model").get("read")
            if "*" not in read_access_list:
                try:
                    queryset = self.queryset.filter(uuid__in=read_access_list)
                except ValidationError as queryset_error:
                    LOG.error(queryset_error)
                    raise queryset_error
        return queryset

    @method_decorator(never_cache)
    def create(self, request, *args, **kwargs):
        """Create a rate."""
        return super().create(request=request, args=args, kwargs=kwargs)

    @method_decorator(never_cache)
    def list(self, request, *args, **kwargs):
        """Obtain the list of rates for the tenant."""
        try:
            response = super().list(request=request, args=args, kwargs=kwargs)
        except ValidationError:
            raise CostModelProviderQueryException("Invalid provider uuid")

        return response

    @method_decorator(never_cache)
    def retrieve(self, request, *args, **kwargs):
        """Get a rate."""
        return super().retrieve(request=request, args=args, kwargs=kwargs)

    @method_decorator(never_cache)
    def destroy(self, request, *args, **kwargs):
        """Delete a rate."""
        uuidParam = kwargs.get("uuid")
        try:
            manager = CostModelManager(cost_model_uuid=uuidParam)
        except CostModel.DoesNotExist:
            LOG.info("CostModel does not exist.")
        except ValidationError as err:
            raise CostModelQueryException(err)
        else:
            manager.update_provider_uuids([])
        return super().destroy(request=request, args=args, kwargs=kwargs)

    @method_decorator(never_cache)
    def update(self, request, *args, **kwargs):
        return super().update(request=request, args=args, kwargs=kwargs)
