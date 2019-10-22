#
# Copyright 2019 Red Hat, Inc.
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
"""Query parameter parsing for query handler."""

import logging
from collections import OrderedDict
from pprint import pformat

from django.core.exceptions import PermissionDenied
from django.utils.translation import ugettext as _
from querystring_parser import parser
from rest_framework.serializers import ValidationError
from tenant_schemas.utils import tenant_context

from api.models import Tenant, User
from api.report.queries import ReportQueryHandler

LOG = logging.getLogger(__name__)


class QueryParameters:
    """Query parameter container object.

    This object is responsible for receiving request data from the
    Views, validating the request parameters, and arranging the request
    parameters for use by the QueryHandler objects.

    """

    def __init__(self, request, caller):
        """Constructor.

        Validated parameters will be set in the `parameters` attribute.

        Args:
            request (Request) the HttpRequest object
            caller (ReportView) the View object handling the request

        """
        self._tenant = None
        self._parameters = OrderedDict()

        self.request = request
        self.report_type = caller.report
        self.serializer = caller.serializer
        self.query_handler = caller.query_handler
        self.tag_handler = caller.tag_handler

        self.tag_keys = []
        if self.report_type != 'tags':
            for tag_model in self.tag_handler:
                self.tag_keys.extend(self._get_tag_keys(tag_model))

        self._validate()   # sets self.parameters

        for item in ['filter', 'group_by', 'order_by']:
            if item not in self.parameters:
                self.parameters[item] = OrderedDict()

        # configure access params.
        if self.access:
            provider = caller.query_handler.provider.lower()
            if not hasattr(self, f'_set_access_{provider}'):
                msg = f'Invalid provider "{provider}".'
                raise ValidationError({'details': _(msg)})
            getattr(self, f'_set_access_{provider}')()

        self._set_time_scope_defaults()
        LOG.debug('Query Parameters: %s', self)

    def __repr__(self):
        """Unambiguous representation."""
        out = {}
        fields = ['parameters', 'query_handler', 'report_type',
                  'request', 'serializer', 'tag_handler',
                  'tag_keys']
        for item in fields:
            try:
                out[item] = getattr(self, item)
            except AttributeError:
                pass
        return out

    def __str__(self):
        """Readable representation."""
        return pformat(self.__repr__())

    def _get_tag_keys(self, model):
        """Get a list of tag keys to validate filters."""
        with tenant_context(self.tenant):
            tags = model.objects.values('key')
            tag_list = [':'.join(['tag', tag.get('key')]) for tag in tags]
            tag_list.extend([':'.join(['and:tag', tag.get('key')]) for tag in tags])
            tag_list.extend([':'.join(['or:tag', tag.get('key')]) for tag in tags])
        return tag_list

    def _process_tag_query_params(self, query_params):
        """Reduce the set of tag keys based on those being queried."""
        tag_key_set = set(self.tag_keys)
        param_tag_keys = set()
        for key, value in query_params.items():
            if isinstance(value, (dict, list)):
                for inner_key in value:
                    if inner_key in tag_key_set:
                        param_tag_keys.add(inner_key)
            elif value in tag_key_set:
                param_tag_keys.add(value)
            if key in tag_key_set:
                param_tag_keys.add(key)

        return param_tag_keys

    def _set_access(self, filter_key, access_key, raise_exception=True):
        """Alter query parameters based on user access."""
        access_list = self.access.get(access_key, {}).get('read', [])
        access_filter_applied = False
        if ReportQueryHandler.has_wildcard(access_list):
            return

        # check group by
        group_by = self.parameters.get('group_by', {})
        if group_by.get(filter_key):
            items = set(group_by.get(filter_key))
            result = get_replacement_result(items, access_list, raise_exception)
            if result:
                self.parameters['group_by'][filter_key] = result
                access_filter_applied = True

        if not access_filter_applied:
            if self.parameters.get('filter', {}).get(filter_key):
                items = set(self.get_filter(filter_key))
                result = get_replacement_result(items, access_list, raise_exception)
                if result:
                    self.parameters['filter'][filter_key] = result
            elif access_list:
                self.parameters['filter'][filter_key] = access_list

    def _set_access_aws(self):
        """Alter query parameters based on user access."""
        self._set_access('account', 'aws.account')

    def _set_access_azure(self):
        """Alter query parameters based on user access."""
        self._set_access('subscription_guid', 'azure.subscription_guid')

    def _set_access_ocp(self):
        """Alter query parameters based on user access."""
        params = [('cluster', True), ('node', False), ('project', False)]
        for name, exc in params:
            self._set_access(name, f'openshift.{name}',
                             raise_exception=exc)

    def _set_access_ocp_aws(self):
        """Alter query parameters based on user access."""
        self._set_access_aws()
        self._set_access_ocp()

    def _set_time_scope_defaults(self):
        """Set the default filter parameters."""
        time_scope_units = self.get_filter('time_scope_units')
        time_scope_value = self.get_filter('time_scope_value')
        resolution = self.get_filter('resolution')

        if not time_scope_value:
            if time_scope_units == 'month':
                time_scope_value = -1
            else:
                time_scope_value = -10

        if not time_scope_units:
            if int(time_scope_value) in [-1, -2]:
                time_scope_units = 'month'
            else:
                time_scope_units = 'day'

        if not resolution:
            if int(time_scope_value) in [-1, -2]:
                resolution = 'monthly'
            else:
                resolution = 'daily'

        self.set_filter(time_scope_value=str(time_scope_value),
                        time_scope_units=str(time_scope_units),
                        resolution=str(resolution))

    def _validate(self):
        """Validate query parameters.

        Raises:
            ValidationError

        Returns:
            (Boolean): True if query params are valid, False otherwise
            (Dict): Dictionary parsed from query params string

        """
        try:
            query_params = parser.parse(self.url_data)
        except parser.MalformedQueryStringError:
            LOG.error('Invalid query parameter format %s.', self.url_data)
            error = {'details': _(f'Invalid query parameter format.')}
            raise ValidationError(error)

        if self.tag_keys:
            self.tag_keys = self._process_tag_query_params(query_params)
            qps = self.serializer(data=query_params, tag_keys=self.tag_keys,
                                  context={'request': self.request})
        else:
            qps = self.serializer(data=query_params, context={'request': self.request})

        if not qps.is_valid():
            raise ValidationError(detail=qps.errors)
        self.parameters = qps.data

    @property
    def accept_type(self):
        """Return accept_type property."""
        return self.request.META.get('HTTP_ACCEPT')

    @property
    def access(self):
        """Return access property."""
        return self.request.user.access

    @property
    def delta(self):
        """Return delta property."""
        return self.get('delta')

    @property
    def parameters(self):
        """Return parameters property."""
        return self._parameters

    @parameters.setter
    def parameters(self, dikt):
        """Parameters setter."""
        self._parameters = dikt

    @property
    def tenant(self):
        """Tenant property."""
        if not self._tenant:
            self._tenant = get_tenant(self.user)
        return self._tenant

    @property
    def url_data(self):
        """Get the url_data."""
        return self.request.GET.urlencode()

    @property
    def user(self):
        """Return user property."""
        return self.request.user

    def get(self, item, default=None):
        """Get parameter data, return default if param value is None or empty."""
        if self.parameters.get(item):
            return self.parameters.get(item, default)
        return default

    def get_filter(self, filt, default=None):
        """Get a filter parameter."""
        return self.get('filter', OrderedDict()).get(filt, default)

    def get_group_by(self, key, default=None):
        """Get a group_by parameter key."""
        return self.get('group_by', OrderedDict()).get(key, default)

    def set(self, key, value):
        """Set parameter data."""
        self.parameters[key] = value

    def set_filter(self, **kwargs):
        """Set one or more filter paramters."""
        for key, val in kwargs.items():
            self.parameters['filter'][key] = val


def get_replacement_result(param_res_list, access_list, raise_exception=True):
    """Adjust param list based on access list."""
    if ReportQueryHandler.has_wildcard(param_res_list):
        return access_list
    if not access_list and not raise_exception:
        return list(param_res_list)
    intersection = param_res_list & set(access_list)
    if not intersection:
        raise PermissionDenied()
    return list(intersection)


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
    if tenant:
        return tenant
    raise ValidationError({'details': _('Invalid user definition')})
