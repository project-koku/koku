#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""PostgreSQL database accessor implementation."""
import logging

from koku.reportdb_accessor import ReportDBAccessor

LOG = logging.getLogger(__name__)


class PostgresReportDBAccessor(ReportDBAccessor):
    """PostgreSQL implementation of report database accessor using Django DB API."""

    def connect(self, **kwargs):
        """
        Create PostgreSQL database connection.

        Args:
            **kwargs: Connection parameters (ignored for Django)

        Returns:
            DB-API 2.0 compatible connection object
        """
        from django.db import connection

        schema = kwargs.get('schema')
        if schema and schema != 'default': # in Trino the default schema name is the same as omitting it. We mimic this behavior.
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO %s", [schema])

        return connection

