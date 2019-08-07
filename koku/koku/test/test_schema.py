"""Test custom koku schema generation."""

from unittest.mock import patch

from django.test import TestCase

from api.common.pagination import StandardResultsSetPagination
from api.report.aws.serializers import ParamSerializer
from api.report.aws.view import AWSCostView
from koku.schema import KokuGenerator, KokuPaginatedSchema, KokuReportSchema


class KokuPaginatedSchemaTest(TestCase):
    """Tests for the generated paginated schema."""

    @patch('koku.schema.is_list_view')
    def test_get_paginated_list_response(self, mock_is_list_view):
        """Test the paginated response generation when data is a list."""
        mock_is_list_view.return_value = True

        schema = KokuPaginatedSchema()
        schema.view = ''
        data = {
            'test_data': 'test'
        }
        response = schema._get_paginated_response(
            '/fake/path', 'GET', StandardResultsSetPagination, data
        )

        self.assertEquals(response['properties']['data']['items'], data)

    @patch('koku.schema.is_list_view')
    def test_get_paginated_nonlist_response(self, mock_is_list_view):
        """Test the paginated response generation when data is not a list."""
        mock_is_list_view.return_value = False

        schema = KokuPaginatedSchema()
        schema.view = ''
        data = {
            'test_data': 'test'
        }
        response = schema._get_paginated_response(
            '/fake/path', 'GET', StandardResultsSetPagination, data
        )

        self.assertEquals(response, data)

    def test_get_responses_delete(self,):
        """Test the paginated response generation when method is delete."""
        schema = KokuPaginatedSchema()
        response = schema._get_responses('/fake/path', 'DELETE')
        expected_response = {
            '204': {
                'description': 'Object Deleted.'
            }
        }
        self.assertEquals(response, expected_response)

    @patch('rest_framework.schemas.openapi.AutoSchema._get_serializer')
    @patch('koku.schema.is_list_view')
    def test_get_responses(self, mock_is_list_view, mock_get_serializer):
        """Test the paginated response generation."""
        mock_is_list_view.return_value = False

        schema = KokuPaginatedSchema()
        schema.view = ''

        response = schema._get_responses('/fake/path', 'GET')

        self.assertTrue('200' in response)


class KokuReportSchemaTest(TestCase):
    """Tests for generating the paginated report schema."""

    @patch('api.report.aws.view.AWSCostView.get_serializer')
    def test_get_operation(self, mock_get_serializer):
        """Test the generated koku paginated report schema."""
        mock_get_serializer.return_value = ParamSerializer()
        schema = KokuReportSchema()
        schema.view = AWSCostView

        koku_schema = schema.get_operation('/reports/aws/costs/', 'GET')
        self.assertTrue('200' in koku_schema['responses'])
        self.assertEquals(koku_schema['operationId'], 'Listtypes')

        parameter_names = [parameter['name'] for parameter in koku_schema['parameters']]
        self.assertTrue('limit' in parameter_names)

        response_schema = \
            koku_schema['responses']['200']['content']['application/json']['schema']['properties']

        self.assertEquals(KokuReportSchema.get_empty_object_array(), response_schema['data'])
        meta_names = list(response_schema['meta']['properties'].keys())

        self.assertEquals(meta_names.sort(), parameter_names.sort())


class KokuGeneratorTest(TestCase):
    """Tests for the schema generator."""

    def test_get_schema(self):
        """Test the schema generator."""
        generator = KokuGenerator(urlconfs=['cost_models.urls', 'api.urls'],)
        schema = generator.get_schema()

        self.assertTrue('servers' in schema)
        self.assertTrue('externalDocs' in schema)
        self.assertTrue('version' in schema['info'])
        self.assertGreater(len(schema['paths'].keys()), 0)
