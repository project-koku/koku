#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Authorization backend resolution logic."""

_VALID_BACKENDS: tuple[str, ...] = ("rbac", "rebac")
DEFAULT_BACKEND: str = "rbac"


def resolve_authorization_backend(onprem: bool, env_value: str) -> str:
    """Return the authorization backend identifier.

    On-prem deployments always use ``"rebac"`` regardless of the environment
    variable.  SaaS deployments honour the env value if it is valid, otherwise
    fall back to ``"rbac"``.
    """
    if onprem:
        return "rebac"
    if env_value in _VALID_BACKENDS:
        return env_value
    return DEFAULT_BACKEND
