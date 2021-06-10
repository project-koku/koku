#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
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
