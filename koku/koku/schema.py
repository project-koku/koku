"""Custom Schema and Generators for Koku's openapi schema."""
import importlib

from django.conf import settings
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.schemas.openapi import AutoSchema, SchemaGenerator
from rest_framework.schemas.utils import is_list_view
from rest_framework.settings import api_settings

from api import API_VERSION


class KokuPaginatedSchema(AutoSchema):
    """Schema Generator for Paginated Koku Responses."""

    def _get_responses(self, path, method):
        """Generate responses that take pagination into account."""
        module_name, class_name = settings.DEFAULT_PAGINATION_CLASS.rsplit('.', 1)
        pagination_module = importlib.import_module(module_name)
        pagination_class = getattr(pagination_module, class_name)

        # If pagination class does not support schemas,
        # just get the drf default response schema.
        if not hasattr(pagination_class, 'get_paginated_response_schema'):
            return super()._get_responses(path, method)

        if method == 'DELETE':
            return {
                '204': {
                    'description': _('Object Deleted.')
                }
            }

        item_schema = {}
        serializer = self._get_serializer(path, method)

        if isinstance(serializer, serializers.Serializer):
            item_schema = self._map_serializer(serializer)
            # No write_only fields for response.
            for name, schema in item_schema['properties'].copy().items():
                if 'writeOnly' in schema:
                    del item_schema['properties'][name]
                    if 'required' in item_schema:
                        item_schema['required'] = [f for f in item_schema['required'] if f != name]

        response_schema = self._get_paginated_response(
            path, method, pagination_class, item_schema
        )

        return {
            '200': {
                'content': {
                    ct: {'schema': response_schema}
                    for ct in self.content_types
                },
                'description':
                    _('Successful Response for %s.') % self._get_operation_id(path, method)
            }
        }

    def _get_paginated_response(self, path, method, pagination_class, data):
        """Get the paginated response schema."""
        if is_list_view(path, method, self.view):
            response = {
                'type': 'array',
                'items': data,
            }
            response_schema = pagination_class.get_paginated_response_schema(
                response
            )
        else:
            response_schema = data
        return response_schema


class KokuReportSchema(KokuPaginatedSchema):
    """A schema generator for koku reports."""

    def get_operation(self, path, method):
        """Get the operations for koku reports."""
        operation = super().get_operation(path, method)
        if 'parameters' in operation:
            operation['parameters'] += self._get_koku_report_filter_query()

        return operation

    def _get_koku_report_filter_query(self):
        """
        Get koku report specific filter queries.

        Koku does not use a backend for filtering. The best way to get up to date
        query filters is to look at the query field in the report serializer. Note
        that the report serializers only serializes query parameters and does not
        serialize the responses.
        """
        serializer = self.view.get_serializer()
        item_schema = self._map_serializer(serializer)
        parameters = item_schema['properties']
        query_params = []

        # For each field in the seralizer generate the filter schema.
        for name, parameter in parameters.items():
            filter_query = {
                'name': name,
                'in': 'query',
                'description':
                    _('The  URL encoded %s to apply to the query') % name,
                'schema': parameter,
            }
            query_params.append(filter_query)
        return query_params

    def _get_paginated_response(self, path, method, pagination_class, data):
        """
        Get the paginated schema.

        Note that data is not serialized so there is no great way of getting it.
        Always pass an empty object array as data. The query fields from the
        serializer goes under meta in the paginator.
        """
        response_schema = pagination_class.get_paginated_response_schema(
            self.get_empty_object_array(), data
        )

        return response_schema

    @staticmethod
    def get_empty_object_array():
        """Get an empty object array schema."""
        return {
            'type': 'array',
            'items': {
                'type': 'object'
            }
        }


class KokuGenerator(SchemaGenerator):
    """The schema generator for Koku."""

    # pylint: disable=too-many-arguments
    def __init__(self, title=None, url=None, description=None,
                 patterns=None, urlconf=None, urlconfs=None):
        """
        Initialize the Koku Schema Generator.

        urlconfs ([string]): the array of url configurations to
        look at when generating the schema
        """
        self.urlconfs = urlconfs
        super().__init__(
            title=title,
            url=url,
            description=description,
            patterns=patterns,
            urlconf=urlconf
        )

    def _initialise_endpoints(self):
        """Initialize the endpoints by looking at all urls in the urlconfs array."""
        if self.endpoints is None:
            self.endpoints = []
            for url in self.urlconfs:
                inspector = self.endpoint_inspector_cls(self.patterns, url)
                self.endpoints += inspector.get_api_endpoints()

    def get_schema(self, request=None, public=False):
        """Generate a OpenAPI schema."""
        schema = super().get_schema(request, public)

        schema['servers'] = self.get_servers()
        schema['externalDocs'] = self.get_external_docs()

        return schema

    # pylint: disable=no-self-use
    def get_servers(self):
        """Get the koku server uri."""
        servers = [{
            'url': settings.INSIGHTS_URI
        }]
        return servers

    # pylint: disable=no-self-use
    def get_external_docs(self):
        """Get koku external doc information."""
        external_doc = {
            'description': _('Find out more about Cost Management'),
            'url': 'https://github.com/project-koku/'
        }
        return external_doc

    def get_info(self):
        """Get Koku info for schema."""
        info = {
            'title': self.title,
            'version': str(API_VERSION),
            'license': self.get_license()
        }

        if self.description is not None:
            info['description'] = self.description

        return info

    # pylint: disable=no-self-use
    def get_license(self):
        """Get Koku licensing information."""
        koku_license = {
            'name': 'AGPL-3.0',
            'url': 'https://opensource.org/licenses/AGPL-3.0'
        }
        return koku_license

    def has_view_permissions(self, path, method, view):
        """
        Override has_view_permissions to always return True.

        The openapi.spec file should include information on all endpoints
        to anyone who views it regardless of the user permission.
        """
        return True


# pylint: disable=too-many-arguments
def get_koku_schema_view(
        title=None, url=None, description=None, urlconf=None, renderer_classes=None,
        public=False, patterns=None, generator_class=None, urlconfs=None,
        authentication_classes=api_settings.DEFAULT_AUTHENTICATION_CLASSES,
        permission_classes=api_settings.DEFAULT_PERMISSION_CLASSES):
    """Return a schema view generated from multiple sources of urls."""
    generator = generator_class(
        title=title, url=url, description=description,
        urlconf=urlconf, patterns=patterns, urlconfs=urlconfs
    )

    # Avoid import cycle on APIView
    from rest_framework.schemas.views import SchemaView
    return SchemaView.as_view(
        renderer_classes=renderer_classes,
        schema_generator=generator,
        public=public,
        authentication_classes=authentication_classes,
        permission_classes=permission_classes,
    )
