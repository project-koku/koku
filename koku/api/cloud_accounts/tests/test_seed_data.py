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
"""TestCase for seeded Cloud Account data."""
from api.cloud_accounts.models import CloudAccount
from django.test import TestCase


class CloudAccountSeedDataTest(TestCase):
    """Test that database contains the seeded account IDs."""

    AWS_ACCOUNT_ID = "589173575009"

    def testModelContainsAWSCloudAccountSeed(self):
        """
        Check the seed.

        Check that the seeded AWS account ID is stored in
        the database.
        """
        actualValue = CloudAccount.objects.get(name="AWS").value
        self.assertEquals(self.AWS_ACCOUNT_ID, actualValue)
