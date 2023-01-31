#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Report database accessor for ingress reports."""
import logging

from tenant_schemas.utils import schema_context

from masu.database.koku_database_access import KokuDBAccess
from masu.external.date_accessor import DateAccessor
from reporting.ingress.models import IngressReports

LOG = logging.getLogger(__name__)


class IngressReportDBAccessor(KokuDBAccess):
    """Class to interact with the koku database for ingrss report processing statistics."""

    def __init__(self, schema):
        """Access the ingress report database table."""
        self._schema = schema
        super().__init__(self._schema)
        self._table = IngressReports
        self.date_accessor = DateAccessor()

    def get_ingress_reports_for_source(self, source_uuid):
        """Get the ingress reports associated with the provided source uuid."""
        query = self._get_db_obj_query()
        return query.filter(source=source_uuid).first()

    def get_ingress_report_by_id(self, ingress_report_id):
        """Get the ingress report by id."""
        with schema_context(self._schema):
            query = self._get_db_obj_query()
            return query.filter(uuid=ingress_report_id).first()

    def mark_ingress_report_as_completed(self, ingress_report_id):
        """Update the completed timestamp for ingress reports."""
        completed_datetime = self.date_accessor.today_with_timezone("UTC")
        if ingress_report_id:
            ingress_report = self._get_db_obj_query().filter(uuid=ingress_report_id).first()
            if not ingress_report.completed_timestamp:
                ingress_report.completed_timestamp = completed_datetime
                ingress_report.save()
            msg = (
                f"Marking ingress report {ingress_report.uuid} "
                f"\nfor provider {ingress_report.source} "
                f"\ncompleted_datetime: {ingress_report.completed_timestamp}."
            )
            LOG.info(msg)
