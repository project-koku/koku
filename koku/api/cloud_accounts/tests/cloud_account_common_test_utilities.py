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
"""Common functions for test cases to re-use."""
from api.cloud_accounts.models import CloudAccount


class CloudAccountCommonTestUtilities:
    """Common functions that test cases re-use."""

    def create_cloud_account(
        self, name="TEST_AWS_ACCOUNT_ID", value="TEST_12345678910", description="TEST Cost Management's AWS Account ID"
    ):
        """Create a model for tests."""
        cloud_account = CloudAccount.objects.create(name=name, value=value, description=description)
        cloud_account.save()
        return cloud_account
