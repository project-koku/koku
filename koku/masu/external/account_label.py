#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Account label interface for masu to consume."""
from api.models import Provider
from masu.external.accounts.labels.aws.aws_account_alias import AWSAccountAlias


class AccountLabel:
    """Object to retreive and save account aliases."""

    def __init__(self, auth, schema_name, provider_type):
        """Set the CUR accounts external source."""
        self.auth = auth
        self.schema_name = schema_name
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
            return AWSAccountAlias(credentials=self.auth, schema_name=self.schema_name)
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
