#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""HCS Processor Exceptions."""


class HCSTableNotFoundError(Exception):
    """HCS table not found error."""

    def __init__(self, table_name, message="table not found"):
        self.table_name = table_name
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f"{self.table_name} {self.message}"
