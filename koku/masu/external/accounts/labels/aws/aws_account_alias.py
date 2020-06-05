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
"""AWS Account aliases resolver."""
from masu.database.account_alias_accessor import AccountAliasAccessor
from masu.util.aws.common import get_account_alias_from_role_arn
from masu.util.aws.common import get_account_names_by_organization


class AWSAccountAlias:
    """AWS account alias resolver."""

    def __init__(self, role_arn, schema_name):
        """
        Object to find account alias for the RoleARN's account id.

        Args:
            role_arn (String): AWS IAM RoleArn.

        """
        self._role_arn = role_arn
        self._schema = schema_name

    def update_account_alias(self):
        """
        Update the account alias.

        Args:
            None
        Returns:
            (String, String) Account ID, Account Alias

        """
        account_id, account_alias = get_account_alias_from_role_arn(self._role_arn)
        with AccountAliasAccessor(account_id, self._schema) as alias_accessor:
            alias_accessor.set_account_alias(account_alias)

        accounts = get_account_names_by_organization(self._role_arn)
        for account in accounts:
            acct_id = account.get("id")
            acct_alias = account.get("name")
            if acct_id and acct_alias:
                with AccountAliasAccessor(acct_id, self._schema) as alias_accessor:
                    alias_accessor.set_account_alias(acct_alias)

        return account_id, account_alias
