# dikt = {
#     'group_by': OrderedDict([('subscription_guid', ['*'])]),
#     'filter': OrderedDict(
#         [
#             ('time_scope_value', '-10'),
#             ('time_scope_units', 'day'),
#             ('resolution', 'daily'),
#         ]
#     ),
#     'order_by': OrderedDict(),
#     'data': [
#         {'date': '2019-11-03', 'subscription_guids': []},
#         {'date': '2019-11-04', 'subscription_guids': []},
#         {'date': '2019-11-05', 'subscription_guids': []},
#         {'date': '2019-11-06', 'subscription_guids': []},
#         {'date': '2019-11-07', 'subscription_guids': []},
#         {'date': '2019-11-08', 'subscription_guids': []},
#         {'date': '2019-11-09', 'subscription_guids': []},
#         {'date': '2019-11-10', 'subscription_guids': []},
#         {'date': '2019-11-11', 'subscription_guids': []},
#         {'date': '2019-11-12', 'subscription_guids': []},
#     ],
#     'total': {
#         'cost': {'value': 0, 'units': 'USD'},
#         'infrastructure_cost': {'value': 0, 'units': 'USD'},
#         'derived_cost': {'value': 0, 'units': 'USD'},
#         'markup_cost': {'value': 0, 'units': 'USD'},
#     },
# }

from django.test import RequestFactory
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_csv.renderers import CSVRenderer

from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase


class AzureReportViewTest(IamTestCase):
    """Azure report view test cases."""

    NAMES = [
        'reports-openshift-azure-costs',
        'reports-openshift-azure-storage',
        'reports-openshift-azure-instance-type',
        # 'openshift-azure-tags',  # TODO: uncomment when we do tagging
    ]

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
        self.client = APIClient()
        self.factory = RequestFactory()

    def test_get_named_view(self):
        """Test costs reports runs with a customer owner."""
        for name in self.NAMES:
            with self.subTest(name=name):
                url = reverse(name)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_names_invalid_query_param(self):
        """Test costs reports runs with an invalid query param."""
        for name in self.NAMES:
            with self.subTest(name=name):
                query = 'group_by[invalid]=*'
                url = reverse(name) + '?' + query
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_named_csv(self):
        """Test CSV output of inventory named reports."""
        self.client = APIClient(HTTP_ACCEPT='text/csv')
        for name in self.NAMES:
            with self.subTest(name=name):
                url = reverse(name)
                response = self.client.get(url, content_type='text/csv', **self.headers)
                response.render()

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.accepted_media_type, 'text/csv')
                self.assertIsInstance(response.accepted_renderer, CSVRenderer)

    def test_execute_query_w_delta_total(self):
        """Test that delta=total returns deltas."""
        query = 'delta=cost'
        url = reverse('reports-openshift-azure-costs') + '?' + query
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_execute_query_w_delta_bad_choice(self):
        """Test invalid delta value."""
        bad_delta = 'Invalid'
        expected = f'"{bad_delta}" is not a valid choice.'
        query = f'delta={bad_delta}'
        url = reverse('reports-openshift-azure-costs') + '?' + query
        response = self.client.get(url, **self.headers)
        result = str(response.data.get('delta')[0])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(result, expected)