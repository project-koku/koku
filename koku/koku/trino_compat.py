"""Trino client types with placeholders for the PostgreSQL-only on-prem path."""
from koku import settings

__all__ = ["TrinoExternalError", "TrinoQueryError", "TrinoUserError"]

if settings.ONPREM:

    class TrinoExternalError(Exception):
        """Placeholder for the unavailable on-prem Trino client exception."""

    class TrinoQueryError(Exception):
        """Placeholder for the unavailable on-prem Trino client exception."""

    class TrinoUserError(Exception):
        """Placeholder for the unavailable on-prem Trino client exception."""

else:
    from trino.exceptions import TrinoExternalError
    from trino.exceptions import TrinoQueryError
    from trino.exceptions import TrinoUserError
