#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""SUBS daily report builder"""
import logging

from api.common import log_json
from masu.external.date_accessor import DateAccessor

LOG = logging.getLogger(__name__)


class ReportSUBS:
    """Class to write subs daily report summary data."""

    def __init__(self, schema_name, provider, provider_uuid, tracing_id):
        """Establish parquet summary processor."""
        self._schema_name = schema_name
        self._provider = provider.removesuffix("-local")
        self._provider_uuid = provider_uuid
        self._date_accessor = DateAccessor()
        self._tracing_id = tracing_id
        self._context = {"schema": self._schema_name, "provider": self._provider_uuid}

    def generate_report(self, start_date, end_date):
        """Generate SUBS daily report
        :param start_date (str) The date to start populating the table
        :param end_date   (str) The date to end on

        returns (none)
        """

        # TODO: implement logic for SUBS daily report
        LOG.info(
            log_json(
                self._tracing_id,
                msg="generate subs daily report",
                context=self._context,
                start_date=start_date,
                end_date=end_date,
            )
        )
