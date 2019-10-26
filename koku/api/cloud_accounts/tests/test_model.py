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

"""TestCase for Cloud Account Model."""
from django.test import TestCase

from api.cloud_accounts.models import CloudAccount
from api.cloud_accounts.tests.cloud_account_common_test_utilities import CloudAccountCommonTestUtilities


class CloudAccountTest(TestCase):
    """Test creating and reading mock model."""

    def test_cloud_account_creation(self):
        """Test creating and reading a mock model."""
        cloud_account = CloudAccountCommonTestUtilities.create_cloud_account(self)
        self.assertTrue(isinstance(cloud_account, CloudAccount))
        self.assertEqual(cloud_account.name, 'TEST_AWS_ACCOUNT_ID')
        self.assertEqual(cloud_account.value, 'TEST_12345678910')
        self.assertEqual(cloud_account.description, "TEST Cost Management's AWS Account ID")
