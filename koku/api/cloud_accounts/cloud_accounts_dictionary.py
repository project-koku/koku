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
"""Cloud Account Dictionary."""


class CloudAccountsDictionary:
    """Cloud Accounts Dictionary."""

    def __init__(self):
        """Constructs the object"""
        self._mapping = [
            {
                "name": "AWS",
                "value": "589173575009",
                "description": "Cost Management's AWS account ID",
                "updated_timestamp": "2020-03-06T14:41:11.808752Z",
            },
            {
                "name": "AWS_LOCAL",
                "value": "589173575009",
                "description": "Cost Management's AWS_LOCAL account ID",
                "updated_timestamp": "2020-03-06T14:41:11.808752Z",
            },
        ]

    def __len__(self):
        return len(self._mapping)
