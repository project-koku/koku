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
"""Account label interface for masu to consume."""
from api.models import Provider
from masu.external.accounts.labels.aws.aws_account_alias import AWSAccountAlias


class AccountLabel:
    """Object to retreive and save account aliases."""

    def __init__(self, auth, schema, provider_type):
        """Set the CUR accounts external source."""
        self.auth = auth
        self.schema = schema
        self.provider_type = provider_type
        self.label = self._set_labler()

    def _set_labler(self):
        """
        Create the account labeler object.

        Args:
            None

        Returns:
            (Object) : Some object that implements update_account_alias()

        """
        if self.provider_type == Provider.PROVIDER_AWS:
            return AWSAccountAlias(role_arn=self.auth, schema_name=self.schema)
        return None

    def get_label_details(self):
        """
        Return the account label information.

        Args:
            None

        Returns:
            (String, String) Account ID, Account Alias

        """
        if self.label:
            return self.label.update_account_alias()
        return None, None
