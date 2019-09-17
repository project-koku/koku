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
"""Test the AWS Query Handler."""
from uuid import uuid4

from django.core.exceptions import PermissionDenied
from django.test import TestCase

from api.report.access_utils import (update_query_parameters_for_aws,
                                     update_query_parameters_for_azure,
                                     update_query_parameters_for_openshift)


class AwsAccessUtilsTest(TestCase):
    """Test the AWS access utils functions."""

    def test_update_query_parameters_with_wildcard(self):
        """Test wildcard doesn't update query parameters."""
        query_parameters = {
            'group_by': {'account': ['*'], 'region': ['*']}
        }
        access = {
            'aws.account': {'read': ['*']}
        }
        out = update_query_parameters_for_aws(query_parameters, access)
        self.assertEqual(query_parameters, out)

    def test_update_query_parameters_replace_wildcard(self):
        """Test that a group by account wildcard is replaced with only the subset of accounts."""
        query_parameters = {
            'group_by': {'account': ['*'], 'region': ['*']}
        }
        access = {
            'aws.account': {'read': ['account1', 'account2']}
        }
        out = update_query_parameters_for_aws(query_parameters, access)
        expected = {
            'group_by': {'account': ['account1', 'account2'], 'region': ['*']}
        }
        self.assertEqual(expected, out)

    def test_update_query_parameters_gb_filtered_intersection(self):
        """Test that a group by account filtered list is replaced with only the intersection of accounts."""
        query_parameters = {
            'group_by': {'account': ['account1', 'account5'], 'region': ['*']}
        }
        access = {
            'aws.account': {'read': ['account1', 'account2']}
        }
        out = update_query_parameters_for_aws(query_parameters, access)
        expected = {
            'group_by': {'account': ['account1'], 'region': ['*']}
        }
        self.assertEqual(expected, out)

    def test_update_query_parameters_empty_intersection(self):
        """Test that a group by account filtered list causes 403 when empty intersection of accounts."""
        query_parameters = {
            'group_by': {'account': ['account1', 'account5'], 'region': ['*']}
        }
        access = {
            'aws.account': {'read': ['account4', 'account2']}
        }
        with self.assertRaises(PermissionDenied):
            update_query_parameters_for_aws(query_parameters, access)

    def test_update_query_parameters_add_account_filter(self):
        """Test that if no group_by or filter is present a filter of accounts is added."""
        query_parameters = {
            'filter': {'region': ['*']}
        }
        access = {
            'aws.account': {'read': ['account1', 'account2']}
        }
        out = update_query_parameters_for_aws(query_parameters, access)
        expected = {
            'filter': {'account': ['account1', 'account2'], 'region': ['*']}
        }
        self.assertEqual(expected, out)

    def test_update_query_parameters_add_account_filter_obj(self):
        """Test that if no group_by or filter is present a filter of accounts is added."""
        query_parameters = {}
        access = {
            'aws.account': {'read': ['account1', 'account2']}
        }
        out = update_query_parameters_for_aws(query_parameters, access)
        expected = {
            'filter': {'account': ['account1', 'account2']}
        }
        self.assertEqual(expected, out)

    def test_update_query_parameters_filtered_intersection(self):
        """Test that a filter by account filtered list is replaced with only the intersection of accounts."""
        query_parameters = {
            'filter': {'account': ['account1', 'account5'], 'region': ['*']}
        }
        access = {
            'aws.account': {'read': ['account1', 'account2']}
        }
        out = update_query_parameters_for_aws(query_parameters, access)
        expected = {
            'filter': {'account': ['account1'], 'region': ['*']}
        }
        self.assertEqual(expected, out)


class AzureAccessUtilsTest(TestCase):
    """Test the azure access utils functions."""

    def setUp(self):
        super().setUp()
        self.guid1 = uuid4()
        self.guid2 = uuid4()
        self.guid3 = uuid4()
        self.guid4 = uuid4()

    def test_update_query_parameters_with_wildcard(self):
        """Test wildcard doesn't update query parameters."""
        query_parameters = {
            'group_by': {'subscription_guid': ['*'], 'resource_location': ['*']}
        }
        access = {
            'azure.subscription_guid': {'read': ['*']}
        }
        out = update_query_parameters_for_azure(query_parameters, access)
        self.assertEqual(query_parameters, out)

    def test_update_query_parameters_replace_wildcard(self):
        """Test that a group by subscription_guid wildcard is replaced with only the subset of subscription_guids."""
        query_parameters = {
            'group_by': {'subscription_guid': ['*'], 'resource_location': ['*']}
        }
        access = {
            'azure.subscription_guid': {'read': [self.guid1, self.guid2]}
        }
        out = update_query_parameters_for_azure(query_parameters, access)
        expected = {
            'group_by': {'subscription_guid': [self.guid1, self.guid2], 'resource_location': ['*']}
        }
        self.assertEqual(expected, out)

    def test_update_query_parameters_gb_filtered_intersection(self):
        """Test that a group by subscription_guid filtered list is replaced with only the intersection of subscription_guids."""
        query_parameters = {
            'group_by': {'subscription_guid': [self.guid1, self.guid2], 'resource_location': ['*']}
        }
        access = {
            'azure.subscription_guid': {'read': [self.guid1, self.guid3]}
        }
        out = update_query_parameters_for_azure(query_parameters, access)
        expected = {
            'group_by': {'subscription_guid': [self.guid1], 'resource_location': ['*']}
        }
        self.assertEqual(expected, out)

    def test_update_query_parameters_empty_intersection(self):
        """Test that a group by subscription_guid filtered list causes 403 when empty intersection of subscription_guids."""
        query_parameters = {
            'group_by': {'subscription_guid': [self.guid1, self.guid3], 'resource_location': ['*']}
        }
        access = {
            'azure.subscription_guid': {'read': [self.guid2, self.guid4]}
        }
        with self.assertRaises(PermissionDenied):
            update_query_parameters_for_azure(query_parameters, access)

    def test_update_query_parameters_add_subscription_guid_filter(self):
        """Test that if no group_by or filter is present a filter of subscription_guids is added."""
        query_parameters = {
            'filter': {'resource_location': ['*']}
        }
        access = {
            'azure.subscription_guid': {'read': [self.guid1, self.guid2]}
        }
        out = update_query_parameters_for_azure(query_parameters, access)
        expected = {
            'filter': {'subscription_guid': [self.guid1, self.guid2], 'resource_location': ['*']}
        }
        self.assertEqual(expected, out)

    def test_update_query_parameters_add_subscription_guid_filter_obj(self):
        """Test that if no group_by or filter is present a filter of subscription_guids is added."""
        query_parameters = {}
        access = {
            'azure.subscription_guid': {'read': [self.guid1, self.guid2]}
        }
        out = update_query_parameters_for_azure(query_parameters, access)
        expected = {
            'filter': {'subscription_guid': [self.guid1, self.guid2]}
        }
        self.assertEqual(expected, out)

    def test_update_query_parameters_filtered_intersection(self):
        """Test that a filter by subscription_guid filtered list is replaced with only the intersection of subscription_guids."""
        query_parameters = {
            'filter': {'subscription_guid': [self.guid1, self.guid2], 'resource_location': ['*']}
        }
        access = {
            'azure.subscription_guid': {'read': [self.guid1, self.guid3]}
        }
        out = update_query_parameters_for_azure(query_parameters, access)
        expected = {
            'filter': {'subscription_guid': [self.guid1], 'resource_location': ['*']}
        }
        self.assertEqual(expected, out)


class OpenShiftAccessUtilsTest(TestCase):
    """Test the OpenShift access utils functions."""

    def test_update_query_parameters_with_wildcard(self):
        """Test wildcard doesn't update query parameters."""
        query_parameters = {
            'group_by': {'cluster': ['*']}
        }
        access = {
            'openshift.cluster': {'read': ['*']}
        }
        out = update_query_parameters_for_openshift(query_parameters, access)
        self.assertEqual(query_parameters, out)

    def test_update_query_parameters_replace_wildcard(self):
        """Test that a group by cluster wildcard is replaced with only the subset of clusters."""
        query_parameters = {
            'group_by': {'cluster': ['*']}
        }
        access = {
            'openshift.cluster': {'read': ['cluster1', 'cluster2']}
        }
        out = update_query_parameters_for_openshift(query_parameters, access)
        expected = {
            'group_by': {'cluster': ['cluster1', 'cluster2']}
        }
        self.assertEqual(expected, out)

    def test_update_query_parameters_gb_filtered_intersection(self):
        """Test that a group by cluster filtered list is replaced with only the intersection of clusters."""
        query_parameters = {
            'group_by': {'cluster': ['cluster1', 'cluster5']}
        }
        access = {
            'openshift.cluster': {'read': ['cluster1', 'cluster2']}
        }
        out = update_query_parameters_for_openshift(query_parameters, access)
        expected = {
            'group_by': {'cluster': ['cluster1']}
        }
        self.assertEqual(expected, out)

    def test_update_query_parameters_empty_intersection(self):
        """Test that a group by cluster filtered list causes 403 when empty intersection of clusters."""
        query_parameters = {
            'group_by': {'cluster': ['cluster1', 'cluster5']}
        }
        access = {
            'openshift.cluster': {'read': ['cluster4', 'cluster2']}
        }
        with self.assertRaises(PermissionDenied):
            update_query_parameters_for_openshift(query_parameters, access)

    def test_update_query_parameters_empty_intersection_node(self):
        """Test that a group by node filtered list causes filter addition when empty intersection of nodes."""
        query_parameters = {
            'group_by': {'node': ['node1', 'node5']}
        }
        access = {
            'openshift.cluster': {'read': ['cluster4', 'cluster2']},
            'openshift.node': {'read': ['node4', 'node2']}
        }
        with self.assertRaises(PermissionDenied):
            update_query_parameters_for_openshift(query_parameters, access)

    def test_update_query_parameters_no_node(self):
        """Test that a group by node filtered list causes filter addition when empty intersection of nodes."""
        query_parameters = {
            'group_by': {'node': ['node1', 'node5']}
        }
        access = {
            'openshift.cluster': {'read': ['cluster4', 'cluster2']},
        }
        with self.assertRaises(PermissionDenied):
            update_query_parameters_for_openshift(query_parameters, access)

    def test_update_query_parameters_empty_intersection_cluster_node(self):
        """Test that a group by node filtered list causes filter addition when empty intersection of nodes."""
        query_parameters = {
            'filter': {'node': ['node1', 'node5']},
            'group_by': {'cluster': ['*']}
        }
        access = {
            'openshift.cluster': {'read': ['cluster4', 'cluster2']},
            'openshift.node': {'read': ['node4', 'node2']}
        }
        with self.assertRaises(PermissionDenied):
            update_query_parameters_for_openshift(query_parameters, access)

    def test_update_query_parameters_empty_intersection_cluster_node2(self):
        """Test that a group by node filtered list causes filter addition when empty intersection of nodes."""
        query_parameters = {
            'filter': {'node': ['node1']},
            'group_by': {'cluster': ['*']}
        }
        access = {
            'openshift.cluster': {'read': ['cluster4', 'cluster2']}
        }
        out = update_query_parameters_for_openshift(query_parameters, access)
        expected = {'filter': {'node': ['node1']}, 'group_by': {'cluster': ['cluster4', 'cluster2']}}
        self.assertEqual(expected, out)

    def test_update_query_parameters_empty_intersection_project(self):
        """Test that a group by project filtered list causes filter addition when empty intersection of nodes."""
        query_parameters = {
            'group_by': {'project': ['proj1', 'proj5']}
        }
        access = {
            'openshift.cluster': {'read': ['*']},
            'openshift.project': {'read': ['proj4', 'proj2']}
        }
        with self.assertRaises(PermissionDenied):
            update_query_parameters_for_openshift(query_parameters, access)

    def test_update_query_parameters_add_cluster_filter(self):
        """Test that if no group_by or filter is present a filter of cluster is added."""
        query_parameters = {
            'filter': {}
        }
        access = {
            'openshift.cluster': {'read': ['cluster1', 'cluster2']}
        }
        out = update_query_parameters_for_openshift(query_parameters, access)
        expected = {
            'filter': {'cluster': ['cluster1', 'cluster2']}
        }
        self.assertEqual(expected, out)

    def test_update_query_parameters_add_cluster_filter_obj(self):
        """Test that if no group_by or filter is present a filter of cluster is added."""
        query_parameters = {}
        access = {
            'openshift.cluster': {'read': ['cluster1', 'cluster2']}
        }
        out = update_query_parameters_for_openshift(query_parameters, access)
        expected = {
            'filter': {'cluster': ['cluster1', 'cluster2']}
        }
        self.assertEqual(expected, out)

    def test_update_query_parameters_filtered_intersection(self):
        """Test that a filter by cluster filtered list is replaced with only the intersection of cluster."""
        query_parameters = {
            'filter': {'cluster': ['cluster1', 'cluster5']}
        }
        access = {
            'openshift.cluster': {'read': ['cluster1', 'cluster2']}
        }
        out = update_query_parameters_for_openshift(query_parameters, access)
        expected = {
            'filter': {'cluster': ['cluster1']}
        }
        self.assertEqual(expected, out)

    def test_update_query_parameters_add_filter(self):
        """Test that addition of filter when not present."""
        query_parameters = {
            'group_by': {'cluster': ['cluster1']}
        }
        access = {
            'openshift.cluster': {'read': ['cluster1', 'cluster2']},
            'openshift.node': {'read': ['node4']}
        }
        out = update_query_parameters_for_openshift(query_parameters, access)
        expected = {
            'group_by': {'cluster': ['cluster1']},
            'filter': {'node': ['node4']}
        }
        print(out)
        self.assertEqual(expected, out)
