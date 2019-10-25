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

"""TestCase for Seeded Cloud Account Model data"""
from django.test import TestCase

from api.cloud_accounts.models import CloudAccount


class CloudAccountSeedDataTest(TestCase):
    """Test that database contains the seeded account IDs"""
    def testModelContainsAWSCloudAccountSeed(self):
        """Test that the database contains the expected seeded Red Hat's Cost Management AWS Account ID of 589173575009."""
        actualValue = CloudAccount.objects.get(name='AWS').value
        self.assertEquals('589173575009', actualValue)