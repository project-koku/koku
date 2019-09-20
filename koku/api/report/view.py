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

"""View for Reports."""
import logging

from django.views.decorators.vary import vary_on_headers
from django.utils.translation import ugettext as _
from pint.errors import DimensionalityError, UndefinedUnitError
from querystring_parser import parser
from rest_framework import status
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView
from tenant_schemas.utils import tenant_context

from api.common.pagination import ReportPagination, ReportRankedPagination
from api.models import Tenant, User
from api.report.aws.query_handler import AWSReportQueryHandler
from api.report.aws.serializers import QueryParamSerializer
from api.report.azure.query_handler import AzureReportQueryHandler
from api.report.azure.serializers import AzureQueryParamSerializer
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.serializers import (OCPCostQueryParamSerializer,
                                        OCPInventoryQueryParamSerializer)
from api.report.ocp_aws.query_handler import OCPAWSReportQueryHandler
from api.report.ocp_aws.serializers import OCPAWSQueryParamSerializer
from api.tags.aws.queries import AWSTagQueryHandler
from api.tags.azure.queries import AzureTagQueryHandler
from api.tags.ocp.queries import OCPTagQueryHandler
from api.tags.ocp_aws.queries import OCPAWSTagQueryHandler
from api.tags.serializers import (AWSTagsQueryParamSerializer,
                                  AzureTagsQueryParamSerializer,
                                  OCPAWSTagsQueryParamSerializer,
                                  OCPTagsQueryParamSerializer)
from api.utils import UnitConverter
from reporting.provider.aws.models import AWSTagsSummary
from reporting.provider.azure.models import AzureTagsSummary
from reporting.provider.ocp.models import (OCPStorageVolumeClaimLabelSummary,
                                           OCPStorageVolumeLabelSummary,
                                           OCPUsagePodLabelSummary)

LOG = logging.getLogger(__name__)


class ClassMapper(object):
    """Data structure object to organize class references."""

    # main mapping data structure
    # this data should be considered static and read-only.
    CLASS_MAP = [
        {
            'provider': 'aws',
            'reports': [
                {
                    'report': 'default',
                    'serializer': QueryParamSerializer,
                    'query_handler': AWSReportQueryHandler,
                    'tag_handler': [AWSTagsSummary]
                },
                {
                    'report': 'tags',
                    'serializer': AWSTagsQueryParamSerializer,
                    'query_handler': AWSTagQueryHandler,
                    'tag_handler': [AWSTagsSummary]
                }
            ]
        },
        {
            'provider': 'ocp',
            'reports': [
                {
                    'report': 'default',
                    'serializer': OCPInventoryQueryParamSerializer,
                    'query_handler': OCPReportQueryHandler,
                    'tag_handler': [OCPUsagePodLabelSummary,
                                    OCPStorageVolumeClaimLabelSummary,
                                    OCPStorageVolumeLabelSummary]
                },
                {
                    'report': 'costs',
                    'serializer': OCPCostQueryParamSerializer,
                    'query_handler': OCPReportQueryHandler,
                    'tag_handler': [OCPUsagePodLabelSummary,
                                    OCPStorageVolumeClaimLabelSummary,
                                    OCPStorageVolumeLabelSummary]
                },
                {
                    'report': 'tags',
                    'serializer': OCPTagsQueryParamSerializer,
                    'query_handler': OCPTagQueryHandler,
                    'tag_handler': [OCPUsagePodLabelSummary,
                                    OCPStorageVolumeClaimLabelSummary,
                                    OCPStorageVolumeLabelSummary]
                },
                {
                    'report': 'volume',
                    'serializer': OCPInventoryQueryParamSerializer,
                    'query_handler': OCPReportQueryHandler,
                    'tag_handler': [OCPUsagePodLabelSummary,
                                    OCPStorageVolumeClaimLabelSummary,
                                    OCPStorageVolumeLabelSummary]
                }
            ]
        },
        {
            'provider': 'ocp_aws',
            'reports': [
                {
                    'report': 'default',
                    'serializer': OCPAWSQueryParamSerializer,
                    'query_handler': OCPAWSReportQueryHandler,
                    'tag_handler': [AWSTagsSummary]
                },
                {
                    'report': 'instance_type',
                    'serializer': OCPAWSQueryParamSerializer,
                    'query_handler': OCPAWSReportQueryHandler,
                    'tag_handler': [AWSTagsSummary]
                },
                {
                    'report': 'tags',
                    'serializer': OCPAWSTagsQueryParamSerializer,
                    'query_handler': OCPAWSTagQueryHandler,
                    'tag_handler': [AWSTagsSummary]
                },
            ]
        },
        {
            'provider': 'azure',
            'reports': [
                {
                    'report': 'default',
                    'serializer': AzureQueryParamSerializer,
                    'query_handler': AzureReportQueryHandler,
                    'tag_handler': [AzureTagsSummary]
                },
                {
                    'report': 'instance_type',
                    'serializer': AzureQueryParamSerializer,
                    'query_handler': AzureReportQueryHandler,
                    'tag_handler': [AzureTagsSummary]
                },
                {
                    'report': 'tags',
                    'serializer': AzureTagsQueryParamSerializer,
                    'query_handler': AzureTagQueryHandler,
                    'tag_handler': [AzureTagsSummary]
                },
            ]
        }
    ]

    def reports(self, provider):
        """Return list of report dictionaries."""
        for item in self.CLASS_MAP:
            if provider == item.get('provider'):
                return item.get('reports')

    def report_types(self, provider):
        """Return list of report names."""
        reports = self.reports(provider)
        return [rep.get('report') for rep in reports]

    def get_report(self, provider, report):
        """Return the specified report dict.

        Return default report dict if named report not found.

        """
        reports = self.reports(provider)
        for rep in reports:
            if report == rep.get('report'):
                return rep

        if report == 'default':
            # avoid infinite recursion
            return {}

        return self.get_report(provider, 'default')

    def serializer(self, provider, report):
        """Return Serializer class from CLASS_MAP."""
        report = self.get_report(provider, report)
        return report.get('serializer')

    def query_handler(self, provider, report):
        """Return QueryHandler class from CLASS_MAP."""
        report = self.get_report(provider, report)
        return report.get('query_handler')

    def tag_handler(self, provider, report):
        """Return TagHandler class from CLASS_MAP."""
        report = self.get_report(provider, report)
        return report.get('tag_handler')


def get_tag_keys(request, summary_model):
    """Get a list of tag keys to validate filters."""
    tenant = get_tenant(request.user)
    with tenant_context(tenant):
        tags = summary_model.objects.values('key')
        tag_list = [':'.join(['tag', tag.get('key')]) for tag in tags]
        tag_list.extend([':'.join(['and:tag', tag.get('key')]) for tag in tags])
        tag_list.extend([':'.join(['or:tag', tag.get('key')]) for tag in tags])

    return tag_list


def process_query_parameters(url_data, provider_serializer, tag_keys=None, **kwargs):
    """Process query parameters and raise any validation errors.

    Args:
        url_data    (String): the url string
    Returns:
        (Boolean): True if query params are valid, False otherwise
        (Dict): Dictionary parsed from query params string

    """
    try:
        query_params = parser.parse(url_data)
    except parser.MalformedQueryStringError:
        LOG.error('Invalid query parameter format %s.', url_data)
        error = {'details': _(f'Invalid query parameter format.')}
        raise ValidationError(error)

    if tag_keys:
        tag_keys = process_tag_query_params(query_params, tag_keys)
        qps = provider_serializer(data=query_params, tag_keys=tag_keys, context=kwargs)
    else:
        qps = provider_serializer(data=query_params, context=kwargs)

    output = None
    validation = qps.is_valid()
    if not validation:
        output = qps.errors
    else:
        output = qps.data

    return (validation, output)


def process_tag_query_params(query_params, tag_keys):
    """Reduce the set of tag keys based on those being queried."""
    tag_key_set = set(tag_keys)
    param_tag_keys = set()
    for key, value in query_params.items():
        if isinstance(value, dict) or isinstance(value, list):
            for inner_param_key in value:
                if inner_param_key in tag_key_set:
                    param_tag_keys.add(inner_param_key)
        elif value in tag_key_set:
            param_tag_keys.add(value)
        if key in tag_key_set:
            param_tag_keys.add(key)

    return param_tag_keys


def get_paginator(filter_query_params, count):
    """Determine which paginator to use based on query params."""
    if 'offset' in filter_query_params:
        paginator = ReportRankedPagination()
        paginator.count = count
    else:
        paginator = ReportPagination()
    return paginator


def get_tenant(user):
    """Get the tenant for the given user.

    Args:
        user    (DjangoUser): user to get the associated tenant
    Returns:
        (Tenant): Object used to get tenant specific data tables
    Raises:
        (ValidationError): If no tenant could be found for the user

    """
    tenant = None
    if user:
        try:
            customer = user.customer
            tenant = Tenant.objects.get(schema_name=customer.schema_name)
        except User.DoesNotExist:
            pass
    if tenant is None:
        error = {'details': _('Invalid user definition')}
        raise ValidationError(error)
    return tenant


def _find_unit():
    """Find the original unit for a report dataset."""
    unit = None

    def __unit_finder(data):
        nonlocal unit
        if isinstance(data, list):
            for entry in data:
                __unit_finder(entry)
        elif isinstance(data, dict):
            for key in data:
                if key == 'units' and data[key] and unit is None:
                    unit = data[key]
                else:
                    __unit_finder(data[key])
        return unit

    return __unit_finder


def _fill_in_missing_units(unit):
    """Fill in missing unit information."""
    def __unit_filler(data):
        if isinstance(data, list):
            for entry in data:
                __unit_filler(entry)
        elif isinstance(data, dict):
            for key in data:
                if key == 'units':
                    if not data[key]:
                        data[key] = unit
                else:
                    __unit_filler(data[key])
        return data
    return __unit_filler


def _convert_units(converter, data, to_unit):
    """Convert the units in a JSON structured report.

    Args:
        converter (api.utils.UnitConverter) Object doing unit conversion
        data (list,dict): The current block of the report being converted
        to_unit (str): The unit type to convert to

    Returns:
        (dict) The final return will be the unit converted report

    """
    suffix = None
    if isinstance(data, list):
        for entry in data:
            _convert_units(converter, entry, to_unit)
    elif isinstance(data, dict):
        for key in data:
            if key == 'total' and isinstance(data[key], dict):
                total = data[key]
                value = total.get('value')
                from_unit = total.get('units', '')
                if '-Mo' in from_unit:
                    from_unit, suffix = from_unit.split('-')
                new_value = converter.convert_quantity(value, from_unit, to_unit)
                total['value'] = new_value.magnitude
                new_unit = to_unit + '-' + suffix if suffix else to_unit
                total['units'] = new_unit
            elif key == 'total' and not isinstance(data[key], dict):
                total = data[key]
                from_unit = data.get('units', '')
                if '-Mo' in from_unit:
                    from_unit, suffix = from_unit.split('-')
                new_value = converter.convert_quantity(total, from_unit, to_unit)
                data['total'] = new_value.magnitude
                new_unit = to_unit + '-' + suffix if suffix else to_unit
                data['units'] = new_unit
            else:
                _convert_units(converter, data[key], to_unit)

    return data


def _generic_report(request, provider, report):
    """Generically query for reports.

    Args:
        request (Request): The HTTP request object
        provider (String): Provider name (e.g. 'aws' or 'ocp')
        report (String): Report name (e.g. 'cost', 'cpu', 'memory'); used to access ReportMap

    Returns:
        (Response): The report in a Response object

    """
    LOG.debug(f'API: {request.path} USER: {request.user.username}')
    tenant = get_tenant(request.user)

    cm = ClassMapper()
    provider_query_hdlr = cm.query_handler(provider, report)
    provider_parameter_serializer = cm.serializer(provider, report)

    tag_keys = []
    if report != 'tags':
        tag_models = cm.tag_handler(provider, report)
        for tag_model in tag_models:
            tag_keys.extend(get_tag_keys(request, tag_model))

    url_data = request.GET.urlencode()
    validation, params = process_query_parameters(
        url_data,
        provider_parameter_serializer,
        tag_keys,
        request=request
    )

    if not validation:
        return Response(
            data=params,
            status=status.HTTP_400_BAD_REQUEST
        )

    handler = provider_query_hdlr(params,
                                  url_data,
                                  tenant,
                                  accept_type=request.META.get('HTTP_ACCEPT'),
                                  report_type=report,
                                  tag_keys=tag_keys,
                                  access=request.user.access)
    output = handler.execute_query()
    max_rank = handler.max_rank

    if 'units' in params:
        from_unit = _find_unit()(output['data'])
        if from_unit:
            try:
                to_unit = params['units']
                unit_converter = UnitConverter()
                output = _fill_in_missing_units(from_unit)(output)
                output = _convert_units(unit_converter, output, to_unit)
            except (DimensionalityError, UndefinedUnitError):
                error = {'details': _('Unit conversion failed.')}
                raise ValidationError(error)

    paginator = get_paginator(params.get('filter', {}), max_rank)
    paginated_result = paginator.paginate_queryset(output, request)
    LOG.debug(f'DATA: {output}')
    return paginator.get_paginated_response(paginated_result)


class ReportView(APIView):
    """
    A shared view for all koku reports.

    This view maps the serializer based on self.provider and self.report.
    It providers one GET endpoint for the reports.
    """

    @vary_on_headers('User-Agent', 'Cookie')
    def get(self, request):
        """Get Report Data."""
        return _generic_report(request,
                               report=self.report,
                               provider=self.provider)
