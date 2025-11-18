#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Trino database accessor implementation."""
import logging

import trino.dbapi
from koku.reportdb_accessor import ReportDBAccessor

LOG = logging.getLogger(__name__)


class TrinoReportDBAccessor(ReportDBAccessor):
    """Trino implementation of report database accessor."""

    def connect(self, **kwargs):
        """
        Create Trino database connection.

        Args:
            **kwargs: Connection parameters (host, port, catalog, schema, etc.)

        Returns:
            Trino DB-API 2.0 compatible connection object
        """
        return trino.dbapi.connect(**kwargs)
