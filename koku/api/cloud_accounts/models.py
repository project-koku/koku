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

"""Model for Cloud Account."""
from django.db import models


class CloudAccount(models.Model):
    """
    A model representing a cloud account.

    A cloud account value should contain
    the ID of a cloud account so that other systems may allow that ID to access their
    systems for the purpose of Koku gathering data.

    In the example of AWS, a business can give priviledges to Cost Management's
    AWS account so that it can read data from that business's cost data bucket.

    See user story: #1284 https://github.com/project-koku/koku/issues/1284

    An example cloud account is
        name: AWS_ACCOUNT_ID
        value: 012345678910
        description: Cost Management's AWS Account ID
    """

    name = models.CharField(max_length=255, help_text='The name of the attribute')
    value = models.TextField(null=True)
    description = models.TextField(null=True)
    updated_timestamp = models.DateTimeField(auto_now=True, blank=True, null=True)
