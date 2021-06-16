#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Masu Processor Exceptions."""


class MasuProcessingError(Exception):
    """Masu Processing Error."""


class MasuProviderError(Exception):
    """Masu Provider Error."""


class MasuConfigurationError(Exception):
    """Masu Configuration Error."""


class CURAccountsInterfaceError(Exception):
    """CURAccountsInterface error."""


class HasherError(Exception):
    """Hasher Utility class error."""
