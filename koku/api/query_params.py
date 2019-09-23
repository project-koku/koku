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

from django.utils.translation import ugettext as _
from querystring_parser import parser
from rest_framework.serializers import ValidationError
from tenant_schemas.utils import tenant_context

from api.models import Tenant, User

LOG = logging.getLogger(__name__)


class QueryParameters:
    """Query parameter container object.

    This object is responsible for receiving request data from the
    Views, validating the request parameters, and arranging the request
    parameters for use by the QueryHandler objects.

    Args:
        request (Request)
        report_type (String)
        serializer (Object)
        tag_handler (Object)

    """

    def __init__(self, request, report_type, serializer, tag_handler):
        """Constructor."""

        self.request = request
        self.report_type = report_type
        self.serializer = serializer
        self.tag_handler = tag_handler

        self.tag_keys = []
        if self.report_type != 'tags':
            for tag_model in self.tag_handler:
                self.tag_keys.extend(self._get_tag_keys(tag_model))

        validation, params = self._process_query_parameters()
        if not validation:
            raise ValidationError(detail=params)
        self.parameters = params

    def __repr__(self):
        """Unambiguous representation."""
        # TODO: show the parameter values in output.
        return super().__repr__()

    def __str__(self):
        """Readable representation."""
        # TODO: show the parameter values in output.
        return super().__str__()

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
        raise NotImplementedError    # FIXME

    def _get_tag_keys(self, model):
        """Get a list of tag keys to validate filters."""
        with tenant_context(self.tenant):
            tags = model.objects.values('key')
            tag_list = [':'.join(['tag', tag.get('key')]) for tag in tags]
            tag_list.extend([':'.join(['and:tag', tag.get('key')]) for tag in tags])
            tag_list.extend([':'.join(['or:tag', tag.get('key')]) for tag in tags])
        return tag_list

    @property
    def tenant(self):
        """Get the tenant for the given user.

        Returns:
            (Tenant): Object used to get tenant specific data tables
        Raises:
            (ValidationError): If no tenant could be found for the user

        """
        tenant = None
        if self.user:
            try:
                customer = self.user.customer
                tenant = Tenant.objects.get(schema_name=customer.schema_name)
            except User.DoesNotExist:
                pass
        if tenant is None:
            error = {'details': _('Invalid user definition')}
            raise ValidationError(error)
        return tenant

    @property
    def user(self):
        """Return user property."""
        return self.request.user

    def get_filter(self, filt, default=None):
        """Get a filter parameter."""
        return self.parameters.get('filter').get(filt, default)

    def _process_query_parameters(self):
        """Process query parameters and raise any validation errors.

        Returns:
            (Boolean): True if query params are valid, False otherwise
            (Dict): Dictionary parsed from query params string

        """
        url_data = self.request.GET.urlencode()
        try:
            query_params = parser.parse(url_data)
        except parser.MalformedQueryStringError:
            LOG.error('Invalid query parameter format %s.', url_data)
            error = {'details': _(f'Invalid query parameter format.')}
            raise ValidationError(error)

        if self.tag_keys:
            self.tag_keys = self._process_tag_query_params(query_params)
            qps = self.serializer(data=query_params, tag_keys=self.tag_keys,
                                  context={'request': self.request})
        else:
            qps = self.serializer(data=query_params, context={'request': self.request})

        output = None
        validation = qps.is_valid()
        if not validation:
            output = qps.errors
        else:
            output = qps.data

        return (validation, output)

    def _process_tag_query_params(self, query_params):
        """Reduce the set of tag keys based on those being queried."""
        tag_key_set = set(self.tag_keys)
        param_tag_keys = set()
        for key, value in query_params.items():
            if isinstance(value, (dict, list)):
                for inner_param_key in value:
                    if inner_param_key in tag_key_set:
                        param_tag_keys.add(inner_param_key)
            elif value in tag_key_set:
                param_tag_keys.add(value)
            if key in tag_key_set:
                param_tag_keys.add(key)

        return param_tag_keys
