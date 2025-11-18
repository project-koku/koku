#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Abstract interface for report database accessors."""
from abc import ABC, abstractmethod


class ReportDBAccessor(ABC):
    """Abstract base class for database accessors."""

    @abstractmethod
    def connect(self, **kwargs):
        """
        Create database connection.

        Args:
            **kwargs: Connection parameters (host, port, catalog, schema, etc.)

        Returns:
            DB-API 2.0 compatible connection object
        """
        pass


def get_report_db_accessor():
      from django.conf import settings
      from koku.reportdb_accessor_postgres import PostgresReportDBAccessor
      from koku.reportdb_accessor_trino import TrinoReportDBAccessor

      if settings.ONPREM:
          return PostgresReportDBAccessor()
      else:
          return TrinoReportDBAccessor()