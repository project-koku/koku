#
# Copyright 2020 Red Hat, Inc.
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
"""Test the Report views."""
# from django.test import RequestFactory
from django.urls import reverse
from rest_framework import status

from api.iam.test.iam_test_case import IamTestCase

# from rest_framework.test import APIClient
# from api.common.pagination import ReportPagination
# from api.common.pagination import ReportRankedPagination
# from api.iam.test.iam_test_case import RbacPermissions
# from api.report.view import get_paginator


class TagsViewTest(IamTestCase):
    """Tests the report view."""

    TAGS = [
        # tags
        "aws-tags",
        "azure-tags",
        "openshift-tags",
        "openshift-aws-tags",
        "openshift-azure-tags",
        "openshift-all-tags",
    ]

    TAGS_KEYS = [
        "aws-tags-key",
        "azure-tags-key",
        "openshift-tags-key",
        "openshift-aws-tags-key",
        "openshift-azure-tags-key",
        "openshift-all-tags-key",
    ]

    def test_tags_endpoint_view(self):
        """Test endpoint runs with a customer owner."""
        for tag_endpoint in self.TAGS:
            with self.subTest(endpoint=tag_endpoint):
                url = reverse(tag_endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_tags(self):
        pass
