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

"""TestCase for Cloud Account Model. """
from api.cloud_accounts.models import CloudAccount

from django.test import TestCase

class CloudAccountTest(TestCase):
    """ Test creating and reading mock model """
    def create_cloud_account(self, \
        name='TEST_AWS_ACCOUNT_ID', \
        value='TEST_12345678910', \
        description='TEST Cost Management\'s AWS Account ID'):
        """ Helper method to create a model for tests """
        return CloudAccount.objects.create(name=name, value=value, description=description)

    def test_cloud_account_creation(self):
        """ Test creating and reading a mock model """
        cloud_account = self.create_cloud_account()
        self.assertTrue(isinstance(cloud_account, CloudAccount))
        self.assertEqual(cloud_account.name, 'TEST_AWS_ACCOUNT_ID')
        self.assertEqual(cloud_account.value, 'TEST_12345678910')
        self.assertEqual(cloud_account.description, 'TEST Cost Management\'s AWS Account ID')
