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
"""Test the OCP on AWS Report views."""
import datetime
from urllib.parse import quote_plus, urlencode

from dateutil import relativedelta
from django.db.models import Count, F, Sum
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_csv.renderers import CSVRenderer
from tenant_schemas.utils import tenant_context

from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.query_handler import TruncDayString
from api.report.test.ocp_aws.helpers import OCPAWSReportDataGenerator
from api.utils import DateHelper
from reporting.models import OCPAWSCostLineItemDailySummary


class OCPAWSReportViewTest(IamTestCase):
    """Tests the report view."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        cls.dh = DateHelper()
        cls.ten_days_ago = cls.dh.n_days_ago(cls.dh._now, 9)

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.data_generator = OCPAWSReportDataGenerator(self.tenant)
        self.data_generator.add_data_to_tenant()
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            serializer.save()

    def test_execute_query_ocp_aws_storage(self):
        """Test that OCP on AWS Storage endpoint works."""
        url = reverse('reports-openshift-aws-storage')
        client = APIClient()
        response = client.get(url, **self.headers)

        expected_end_date = self.dh.today.date().strftime('%Y-%m-%d')
        expected_start_date = self.ten_days_ago.strftime('%Y-%m-%d')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        dates = sorted([item.get('date') for item in data.get('data')])
        self.assertEqual(dates[0], expected_start_date)
        self.assertEqual(dates[-1], expected_end_date)

        for item in data.get('data'):
            if item.get('values'):
                values = item.get('values')[0]
                self.assertTrue('usage' in values)
                self.assertTrue('cost' in values)

    def test_execute_query_ocp_aws_storage_last_thirty_days(self):
        """Test that OCP CPU endpoint works."""
        url = reverse('reports-openshift-aws-storage')
        client = APIClient()
        params = {'filter[time_scope_value]': '-30',
                  'filter[time_scope_units]': 'day',
                  'filter[resolution]': 'daily'}
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)

        expected_end_date = self.dh.today
        expected_start_date = self.dh.n_days_ago(expected_end_date, 29)
        expected_end_date = str(expected_end_date.date())
        expected_start_date = str(expected_start_date.date())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        dates = sorted([item.get('date') for item in data.get('data')])
        self.assertEqual(dates[0], expected_start_date)
        self.assertEqual(dates[-1], expected_end_date)

        for item in data.get('data'):
            if item.get('values'):
                values = item.get('values')[0]
                self.assertTrue('usage' in values)
                self.assertTrue('cost' in values)

    def test_execute_query_ocp_aws_storage_this_month(self):
        """Test that data is returned for the full month."""
        url = reverse('reports-openshift-aws-storage')
        client = APIClient()
        params = {
            'filter[resolution]': 'monthly',
            'filter[time_scope_value]': '-1',
            'filter[time_scope_units]': 'month'
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)

        expected_date = self.dh.today.strftime('%Y-%m')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        dates = sorted([item.get('date') for item in data.get('data')])
        self.assertEqual(dates[0], expected_date)

        values = data.get('data')[0].get('values')[0]
        self.assertTrue('usage' in values)
        self.assertTrue('cost' in values)

    def test_execute_query_ocp_aws_storage_this_month_daily(self):
        """Test that data is returned for the full month."""
        url = reverse('reports-openshift-aws-storage')
        client = APIClient()
        params = {
            'filter[resolution]': 'daily',
            'filter[time_scope_value]': '-1',
            'filter[time_scope_units]': 'month'
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)

        expected_start_date = self.dh.this_month_start.strftime('%Y-%m-%d')
        expected_end_date = self.dh.today.strftime('%Y-%m-%d')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        dates = sorted([item.get('date') for item in data.get('data')])
        self.assertEqual(dates[0], expected_start_date)
        self.assertEqual(dates[-1], expected_end_date)

        for item in data.get('data'):
            if item.get('values'):
                values = item.get('values')[0]
                self.assertTrue('usage' in values)
                self.assertTrue('cost' in values)

    def test_execute_query_ocp_aws_storage_last_month(self):
        """Test that data is returned for the last month."""
        url = reverse('reports-openshift-aws-storage')
        client = APIClient()
        params = {
            'filter[resolution]': 'monthly',
            'filter[time_scope_value]': '-2',
            'filter[time_scope_units]': 'month'
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)

        expected_date = self.dh.last_month_start.strftime('%Y-%m')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        dates = sorted([item.get('date') for item in data.get('data')])
        self.assertEqual(dates[0], expected_date)

        values = data.get('data')[0].get('values')[0]
        self.assertTrue('usage' in values)
        self.assertTrue('cost' in values)

    def test_execute_query_ocp_aws_storage_last_month_daily(self):
        """Test that data is returned for the full month."""
        url = reverse('reports-openshift-aws-storage')
        client = APIClient()
        params = {
            'filter[resolution]': 'daily',
            'filter[time_scope_value]': '-2',
            'filter[time_scope_units]': 'month'
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)

        expected_start_date = self.dh.last_month_start.strftime('%Y-%m-%d')
        expected_end_date = self.dh.last_month_end.strftime('%Y-%m-%d')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        dates = sorted([item.get('date') for item in data.get('data')])
        self.assertEqual(dates[0], expected_start_date)
        self.assertEqual(dates[-1], expected_end_date)

        for item in data.get('data'):
            if item.get('values'):
                values = item.get('values')[0]
                self.assertTrue('usage' in values)
                self.assertTrue('cost' in values)

    def test_execute_query_ocp_aws_storage_group_by_limit(self):
        """Test that OCP Mem endpoint works with limits."""
        url = reverse('reports-openshift-aws-storage')
        client = APIClient()
        params = {
            'group_by[node]': '*',
            'filter[limit]': '1',
            'filter[time_scope_units]': 'day',
            'filter[time_scope_value]': '-10',
            'filter[resolution]': 'daily'
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        data = response.json()

        with tenant_context(self.tenant):
            totals = OCPAWSCostLineItemDailySummary.objects\
                .filter(usage_start__gte=self.ten_days_ago)\
                .filter(product_family__contains='Storage')\
                .values(*['usage_start'])\
                .annotate(usage=Sum('usage_amount'))

        totals = {total.get('usage_start').strftime('%Y-%m-%d'): total.get('usage')
                  for total in totals}

        self.assertIn('nodes', data.get('data')[0])

        # Check if limit returns the correct number of results, and
        # that the totals add up properly
        for item in data.get('data'):
            if item.get('nodes'):
                date = item.get('date')
                projects = item.get('nodes')
                self.assertTrue(len(projects) <= 2)
                if len(projects) == 2:
                    self.assertEqual(projects[1].get('node'), '1 Other')
                    usage_total = projects[0].get('values')[0].get('usage', {}).get('value') + \
                        projects[1].get('values')[0].get('usage', {}).get('value')
                    self.assertEqual(round(usage_total, 3),
                                     round(float(totals.get(date)), 3))

    def test_execute_query_ocp_aws_storage_with_delta(self):
        """Test that deltas work for OpenShift on AWS storage."""
        url = reverse('reports-openshift-aws-storage')
        client = APIClient()
        params = {
            'delta': 'usage',
            'filter[resolution]': 'daily',
            'filter[time_scope_value]': '-1',
            'filter[time_scope_units]': 'month'
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        this_month_start = self.dh.this_month_start
        last_month_start = self.dh.last_month_start

        date_delta = relativedelta.relativedelta(months=1)

        def date_to_string(dt):
            return dt.strftime('%Y-%m-%d')

        def string_to_date(dt):
            return datetime.datetime.strptime(dt, '%Y-%m-%d').date()

        with tenant_context(self.tenant):
            current_total = OCPAWSCostLineItemDailySummary.objects\
                .filter(usage_start__gte=this_month_start)\
                .filter(product_family__contains='Storage')\
                .aggregate(usage=Sum(F('usage_amount')))\
                .get('usage')
            current_total = current_total if current_total is not None else 0

            current_totals = OCPAWSCostLineItemDailySummary.objects\
                .filter(usage_start__gte=this_month_start)\
                .filter(product_family__contains='Storage')\
                .annotate(**{'date': TruncDayString('usage_start')})\
                .values(*['date'])\
                .annotate(usage=Sum(F('usage_amount')))

            prev_totals = OCPAWSCostLineItemDailySummary.objects\
                .filter(usage_start__gte=last_month_start)\
                .filter(usage_start__lt=this_month_start)\
                .filter(product_family__contains='Storage')\
                .annotate(**{'date': TruncDayString('usage_start')})\
                .values(*['date'])\
                .annotate(usage=Sum(F('usage_amount')))

        current_totals = {total.get('date'): total.get('usage')
                          for total in current_totals}
        prev_totals = {date_to_string(string_to_date(total.get('date')) + date_delta): total.get('usage')
                       for total in prev_totals
                       if date_to_string(string_to_date(total.get('date')) + date_delta) in current_totals}

        prev_total = sum(prev_totals.values())
        prev_total = prev_total if prev_total is not None else 0

        expected_delta = current_total - prev_total
        delta = data.get('meta', {}).get('delta', {}).get('value')
        self.assertEqual(round(delta, 3), round(float(expected_delta), 3))
        for item in data.get('data'):
            date = item.get('date')
            expected_delta = current_totals.get(date, 0) - prev_totals.get(date, 0)
            values = item.get('values', [])
            delta_value = 0
            if values:
                delta_value = values[0].get('delta_value')
            self.assertEqual(round(delta_value, 3), round(float(expected_delta), 3))

    def test_execute_query_ocp_aws_storage_group_by_project(self):
        """Test that grouping by project filters data."""
        with tenant_context(self.tenant):
            # Force Django to do GROUP BY to get nodes
            projects = OCPAWSCostLineItemDailySummary.objects\
                .filter(usage_start__gte=self.ten_days_ago)\
                .filter(product_family__contains='Storage')\
                .values(*['namespace'])\
                .annotate(project_count=Count('namespace'))\
                .all()
            project_of_interest = projects[0].get('namespace')

        url = reverse('reports-openshift-aws-storage')
        client = APIClient()
        params = {'group_by[project]': project_of_interest}

        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        for entry in data.get('data', []):
            for project in entry.get('projects', []):
                self.assertEqual(project.get('project'), project_of_interest)

    def test_execute_query_ocp_aws_storage_group_by_cluster(self):
        """Test that grouping by cluster filters data."""
        with tenant_context(self.tenant):
            # Force Django to do GROUP BY to get nodes
            clusters = OCPAWSCostLineItemDailySummary.objects\
                .filter(usage_start__gte=self.ten_days_ago)\
                .filter(product_family__contains='Storage')\
                .values(*['cluster_id'])\
                .annotate(cluster_count=Count('cluster_id'))\
                .all()
            cluster_of_interest = clusters[0].get('cluster_id')

        url = reverse('reports-openshift-aws-storage')
        client = APIClient()
        params = {'group_by[cluster]': cluster_of_interest}

        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        for entry in data.get('data', []):
            for cluster in entry.get('clusters', []):
                self.assertEqual(cluster.get('cluster'), cluster_of_interest)

    def test_execute_query_group_by_pod_fails(self):
        """Test that grouping by pod filters data."""
        url = reverse('reports-openshift-aws-storage')
        client = APIClient()
        params = {'group_by[pod]': '*'}

        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_execute_query_ocp_aws_storage_group_by_node(self):
        """Test that grouping by node filters data."""
        with tenant_context(self.tenant):
            # Force Django to do GROUP BY to get nodes
            nodes = OCPAWSCostLineItemDailySummary.objects\
                .values(*['node'])\
                .filter(usage_start__gte=self.ten_days_ago)\
                .filter(product_family__contains='Storage')\
                .values(*['node'])\
                .annotate(node_count=Count('node'))\
                .all()
            node_of_interest = nodes[0].get('node')

        url = reverse('reports-openshift-aws-storage')
        client = APIClient()
        params = {'group_by[node]': node_of_interest}

        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        for entry in data.get('data', []):
            for node in entry.get('nodes', []):
                self.assertEqual(node.get('node'), node_of_interest)

    def test_execute_query_ocp_aws_storage_with_tag_filter(self):
        """Test that data is filtered by tag key."""
        with tenant_context(self.tenant):
            labels = OCPAWSCostLineItemDailySummary.objects\
                .filter(usage_start__gte=self.ten_days_ago)\
                .filter(product_family__contains='Storage')\
                .values(*['tags'])\
                .first()

            tags = labels.get('tags')
            filter_key = list(tags.keys())[0]
            filter_value = tags.get(filter_key)

            totals = OCPAWSCostLineItemDailySummary.objects\
                .filter(usage_start__gte=self.ten_days_ago)\
                .filter(**{f'tags__{filter_key}': filter_value})\
                .filter(product_family__contains='Storage')\
                .aggregate(
                    **{
                        'usage': Sum('usage_amount'),
                        'cost': Sum('unblended_cost')
                    }
                )

        url = reverse('reports-openshift-aws-storage')
        client = APIClient()
        params = {f'filter[tag:{filter_key}]': filter_value}

        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        data_totals = data.get('meta', {}).get('total', {})
        for key in totals:
            expected = float(totals[key])
            result = data_totals.get(key, {}).get('value')
            self.assertEqual(result, expected)

    def test_execute_query_ocp_aws_storage_with_wildcard_tag_filter(self):
        """Test that data is filtered to include entries with tag key."""
        with tenant_context(self.tenant):
            labels = OCPAWSCostLineItemDailySummary.objects\
                .filter(usage_start__gte=self.ten_days_ago)\
                .filter(product_family__contains='Storage')\
                .values(*['tags'])\
                .first()

            tags = labels.get('tags')
            filter_key = list(tags.keys())[0]

            totals = OCPAWSCostLineItemDailySummary.objects\
                .filter(usage_start__gte=self.ten_days_ago)\
                .filter(**{'tags__has_key': filter_key})\
                .filter(product_family__contains='Storage')\
                .aggregate(
                    **{
                        'usage': Sum('usage_amount'),
                        'cost': Sum('unblended_cost')
                    }
                )

        url = reverse('reports-openshift-aws-storage')
        client = APIClient()
        params = {f'filter[tag:{filter_key}]': '*'}

        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        data_totals = data.get('meta', {}).get('total', {})
        for key in totals:
            expected = float(totals[key])
            result = data_totals.get(key, {}).get('value')
            self.assertEqual(result, expected)

    def test_execute_query_ocp_aws_storage_with_tag_group_by(self):
        """Test that data is grouped by tag key."""
        with tenant_context(self.tenant):
            labels = OCPAWSCostLineItemDailySummary.objects\
                .filter(usage_start__gte=self.ten_days_ago)\
                .filter(product_family__contains='Storage')\
                .values(*['tags'])\
                .first()

            tags = labels.get('tags')
            group_by_key = list(tags.keys())[0]

        url = reverse('reports-openshift-aws-storage')
        client = APIClient()
        params = {f'group_by[tag:{group_by_key}]': '*'}

        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        data = data.get('data', [])
        expected_keys = ['date', group_by_key + 's']
        for entry in data:
            self.assertEqual(list(entry.keys()), expected_keys)

    def test_execute_query_ocp_aws_storage_with_group_by_tag_and_limit(self):
        """Test that data is grouped by tag key and limited."""
        with tenant_context(self.tenant):
            labels = OCPAWSCostLineItemDailySummary.objects\
                .filter(usage_start__gte=self.dh.last_month_start)\
                .filter(usage_start__lte=self.dh.last_month_end)\
                .filter(product_family__contains='Storage')\
                .values(*['tags'])\
                .first()

            tags = labels.get('tags')
            group_by_key = list(tags.keys())[0]
            plural_key = group_by_key + 's'

        url = reverse('reports-openshift-aws-storage')
        client = APIClient()
        params = {
            'filter[resolution]': 'monthly',
            'filter[time_scope_value]': '-2',
            'filter[time_scope_units]': 'month',
            f'group_by[tag:{group_by_key}]': '*',
            'filter[limit]': 2
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        data = data.get('data', [])
        # default ordered by usage
        previous_tag_usage = data[0].get(plural_key, [])[0].get('values', [{}])[0].get('usage', {}).get('value')
        for entry in data[0].get(plural_key, []):
            current_tag_usage = entry.get('values', [{}])[0].get('usage', {}).get('value')
            if 'Other' not in entry.get(group_by_key):
                self.assertTrue(current_tag_usage <= previous_tag_usage)
                previous_tag_usage = current_tag_usage

    def test_execute_query_ocp_aws_storage_with_group_by_and_limit(self):
        """Test that data is grouped by and limited."""
        url = reverse('reports-openshift-aws-storage')
        client = APIClient()
        params = {
            'group_by[node]': '*',
            'filter[limit]': 1,
            'filter[resolution]': 'monthly',
            'filter[time_scope_value]': '-2',
            'filter[time_scope_units]': 'month',
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        data = data.get('data', [])
        for entry in data:
            other = entry.get('nodes', [])[-1:]
            self.assertIn('Other', other[0].get('node'))

    def test_execute_query_ocp_aws_storage_with_group_by_order_by_and_limit(self):
        """Test that data is grouped by and limited on order by."""
        url = reverse('reports-openshift-aws-storage')
        client = APIClient()
        params = {
            'filter[resolution]': 'monthly',
            'filter[time_scope_value]': '-2',
            'filter[time_scope_units]': 'month',
            'group_by[node]': '*',
            'order_by[usage]': 'desc',
            'filter[limit]': 1
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        data = data.get('data', [])
        previous_usage = data[0].get('nodes', [])[0].get('values', [])[0].get('usage', {}).get('value')
        for entry in data[0].get('nodes', []):
            current_usage = entry.get('values', [])[0].get('usage', {}).get('value')
            self.assertTrue(current_usage <= previous_usage)
            previous_usage = current_usage

    def test_get_costs(self):
        """Test costs reports runs with a customer owner."""
        url = reverse('reports-openshift-aws-costs')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get('data'))
        self.assertIsInstance(json_result.get('data'), list)
        self.assertTrue(len(json_result.get('data')) > 0)

    def test_get_costs_invalid_query_param(self):
        """Test costs reports runs with an invalid query param."""
        qs = 'group_by%5Binvalid%5D=account1&filter%5Bresolution%5D=daily'
        url = reverse('reports-openshift-aws-costs') + '?' + qs
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_costs_csv(self):
        """Test CSV output of costs reports."""
        url = reverse('reports-openshift-aws-costs')
        client = APIClient(HTTP_ACCEPT='text/csv')

        response = client.get(url, **self.headers)
        response.render()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.accepted_media_type, 'text/csv')
        self.assertIsInstance(response.accepted_renderer, CSVRenderer)

    def test_execute_query_ocp_aws_costs_group_by_project(self):
        """Test that grouping by project filters data."""
        with tenant_context(self.tenant):
            # Force Django to do GROUP BY to get nodes
            projects = OCPAWSCostLineItemDailySummary.objects\
                .filter(usage_start__gte=self.ten_days_ago)\
                .values(*['namespace'])\
                .annotate(project_count=Count('namespace'))\
                .all()
            project_of_interest = projects[0].get('namespace')

        url = reverse('reports-openshift-aws-costs')
        client = APIClient()
        params = {'group_by[project]': project_of_interest}

        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        for entry in data.get('data', []):
            for project in entry.get('projects', []):
                self.assertEqual(project.get('project'), project_of_interest)

    def test_execute_query_ocp_aws_instance_type(self):
        """Test that the instance type API runs."""
        url = reverse('reports-openshift-aws-instance-type')
        client = APIClient()
        response = client.get(url, **self.headers)

        expected_end_date = self.dh.today.date().strftime('%Y-%m-%d')
        expected_start_date = self.ten_days_ago.strftime('%Y-%m-%d')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        dates = sorted([item.get('date') for item in data.get('data')])
        self.assertEqual(dates[0], expected_start_date)
        self.assertEqual(dates[-1], expected_end_date)

        for item in data.get('data'):
            if item.get('values'):
                values = item.get('values')[0]
                self.assertTrue('usage' in values)
                self.assertTrue('cost' in values)
                self.assertTrue('count' in values)

    def test_execute_query_ocp_aws_instance_type_by_project(self):
        """Test that the instance type API runs when grouped by project."""
        with tenant_context(self.tenant):
            # Force Django to do GROUP BY to get nodes
            projects = OCPAWSCostLineItemDailySummary.objects\
                .filter(usage_start__gte=self.ten_days_ago)\
                .filter(product_family__contains='Storage')\
                .values(*['namespace'])\
                .annotate(project_count=Count('namespace'))\
                .all()
            project_of_interest = projects[0].get('namespace')

        url = reverse('reports-openshift-aws-instance-type')
        client = APIClient()
        params = {'group_by[project]': project_of_interest}

        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        for entry in data.get('data', []):
            for project in entry.get('projects', []):
                self.assertEqual(project.get('project'), project_of_interest)

    def test_execute_query_default_pagination(self):
        """Test that the default pagination works."""
        url = reverse('reports-openshift-aws-instance-type')
        client = APIClient()
        params = {
            'filter[resolution]': 'monthly',
            'filter[time_scope_value]': '-1',
            'filter[time_scope_units]': 'month',
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)

        response_data = response.json()
        data = response_data.get('data', [])
        meta = response_data.get('meta', {})
        count = meta.get('count', 0)

        self.assertIn('total', meta)
        self.assertIn('filter', meta)
        self.assertIn('count', meta)

        self.assertEqual(len(data), count)

    def test_execute_query_limit_pagination(self):
        """Test that the default pagination works with a limit."""
        limit = 5
        start_date = self.dh.this_month_start.date().strftime('%Y-%m-%d')
        url = reverse('reports-openshift-aws-instance-type')
        client = APIClient()
        params = {
            'filter[resolution]': 'daily',
            'filter[time_scope_value]': '-1',
            'filter[time_scope_units]': 'month',
            'limit': limit
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)

        response_data = response.json()
        data = response_data.get('data', [])
        meta = response_data.get('meta', {})
        count = meta.get('count', 0)

        self.assertIn('total', meta)
        self.assertIn('filter', meta)
        self.assertIn('count', meta)

        self.assertNotEqual(len(data), count)
        if limit > count:
            self.assertEqual(len(data), count)
        else:
            self.assertEqual(len(data), limit)
        self.assertEqual(data[0].get('date'), start_date)

    def test_execute_query_limit_offset_pagination(self):
        """Test that the default pagination works with an offset."""
        limit = 5
        offset = 5
        start_date = (self.dh.this_month_start + datetime.timedelta(days=5))\
            .date()\
            .strftime('%Y-%m-%d')
        url = reverse('reports-openshift-aws-instance-type')
        client = APIClient()
        params = {
            'filter[resolution]': 'daily',
            'filter[time_scope_value]': '-1',
            'filter[time_scope_units]': 'month',
            'limit': limit,
            'offset': offset
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)

        response_data = response.json()
        data = response_data.get('data', [])
        meta = response_data.get('meta', {})
        count = meta.get('count', 0)

        self.assertIn('total', meta)
        self.assertIn('filter', meta)
        self.assertIn('count', meta)

        self.assertNotEqual(len(data), count)
        if limit + offset > count:
            self.assertEqual(len(data), max((count - offset), 0))
        else:
            self.assertEqual(len(data), limit)
        self.assertEqual(data[0].get('date'), start_date)

    def test_execute_query_filter_limit_offset_pagination(self):
        """Test that the ranked group pagination works."""
        limit = 1
        offset = 0

        url = reverse('reports-openshift-aws-instance-type')
        client = APIClient()
        params = {
            'filter[resolution]': 'monthly',
            'filter[time_scope_value]': '-1',
            'filter[time_scope_units]': 'month',
            'group_by[project]': '*',
            'filter[limit]': limit,
            'filter[offset]': offset
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)

        response_data = response.json()
        data = response_data.get('data', [])
        meta = response_data.get('meta', {})
        count = meta.get('count', 0)

        self.assertIn('total', meta)
        self.assertIn('filter', meta)
        self.assertIn('count', meta)

        for entry in data:
            projects = entry.get('projects', [])
            if limit + offset > count:
                self.assertEqual(len(projects), max((count - offset), 0))
            else:
                self.assertEqual(len(projects), limit)

    def test_execute_query_filter_limit_high_offset_pagination(self):
        """Test that the default pagination works."""
        limit = 1
        offset = 10

        url = reverse('reports-openshift-aws-instance-type')
        client = APIClient()
        params = {
            'filter[resolution]': 'monthly',
            'filter[time_scope_value]': '-1',
            'filter[time_scope_units]': 'month',
            'group_by[project]': '*',
            'filter[limit]': limit,
            'filter[offset]': offset
        }
        url = url + '?' + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)

        response_data = response.json()
        data = response_data.get('data', [])
        meta = response_data.get('meta', {})
        count = meta.get('count', 0)

        self.assertIn('total', meta)
        self.assertIn('filter', meta)
        self.assertIn('count', meta)

        for entry in data:
            projects = entry.get('projects', [])
            if limit + offset > count:
                self.assertEqual(len(projects), max((count - offset), 0))
            else:
                self.assertEqual(len(projects), limit)
