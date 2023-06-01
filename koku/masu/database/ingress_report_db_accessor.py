#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Report database accessor for ingress reports."""
import logging

from django_tenants.utils import schema_context

from masu.database.koku_database_access import KokuDBAccess
from masu.external.date_accessor import DateAccessor
from reporting.ingress.models import IngressReports

LOG = logging.getLogger(__name__)


class IngressReportDBAccessor(KokuDBAccess):
    """Class to interact with the koku database for ingrss report processing statistics."""

    def __init__(self, schema_name):
        """Access the ingress report database table."""
        self._schema_name = schema_name
        super().__init__(self._schema_name)
        self._table = IngressReports
        self.date_accessor = DateAccessor()

    def get_ingress_reports_for_source(self, source_uuid):
        """Get the ingress reports associated with the provided source uuid."""
        query = self._get_db_obj_query()
        return query.filter(source=source_uuid).first()

    def get_ingress_report_by_uuid(self, ingress_report_uuid):
        """Get the ingress report by id."""
        with schema_context(self._schema_name):
            query = self._get_db_obj_query()
            return query.filter(uuid=ingress_report_uuid).first()

    def mark_ingress_report_as_completed(self, ingress_report_uuid):
        """Update the completed timestamp for ingress reports."""
        completed_datetime = self.date_accessor.today_with_timezone("UTC")
        if ingress_report_uuid:
            ingress_report = self._get_db_obj_query().filter(uuid=ingress_report_uuid).first()
            if not ingress_report.completed_timestamp:
                ingress_report.completed_timestamp = completed_datetime
                ingress_report.save()
            msg = (
                f"Marking ingress report {ingress_report.uuid} "
                f"\nfor source {ingress_report.source} "
                f"\ncompleted_datetime: {ingress_report.completed_timestamp}."
            )
            self.update_ingress_report_status(ingress_report_uuid, "Complete")
            LOG.info(msg)

    def update_ingress_report_status(self, ingress_report_uuid, status):
        """Update the status field for ingress reports."""
        if ingress_report_uuid:
            ingress_report = self._get_db_obj_query().filter(uuid=ingress_report_uuid).first()
            ingress_report.status = status
            ingress_report.save()
            msg = (
                f"Updating ingress report {ingress_report.uuid} "
                f"\nfor source {ingress_report.source} "
                f"\nStatus: {ingress_report.status}"
            )
            LOG.info(msg)
