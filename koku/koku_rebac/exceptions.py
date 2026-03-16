#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Custom exceptions for the Kessel ReBAC integration."""


class KesselError(Exception):
    """Base exception for all Kessel-related errors."""

    def __init__(self, message: str = "", *args) -> None:
        self.message = message
        super().__init__(message, *args)


class KesselConnectionError(KesselError):
    """Raised when a gRPC connection to Kessel fails."""
