#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Updates report summary tables in the database."""
import logging
from decimal import Decimal

from dateutil import parser
from django.conf import settings
from tenant_schemas.utils import schema_context

from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.ocp.ocp_cloud_summary_updater import OCPCloudReportSummaryUpdater
from masu.util.aws.common import get_bills_from_provider as aws_get_bills_from_provider
from masu.util.azure.common import get_bills_from_provider as azure_get_bills_from_provider
from masu.util.common import date_range_pair
from masu.util.ocp.common import get_cluster_id_from_provider

LOG = logging.getLogger(__name__)


class OCPCloudParquetReportSummaryUpdater(OCPCloudReportSummaryUpdater):
    """Class to update OCP report summary data."""

    def update_aws_summary_tables(self, openshift_provider_uuid, aws_provider_uuid, start_date, end_date):
        """Update operations specifically for OpenShift on AWS."""
        if isinstance(start_date, str):
            start_date = parser.parse(start_date).date()
        if isinstance(end_date, str):
            end_date = parser.parse(end_date).date()

        cluster_id = get_cluster_id_from_provider(openshift_provider_uuid)
        with OCPReportDBAccessor(self._schema) as accessor:
            report_period = accessor.report_periods_for_provider_uuid(openshift_provider_uuid, start_date)
            accessor.delete_infrastructure_raw_cost_from_daily_summary(
                openshift_provider_uuid, report_period.id, start_date, end_date
            )
        aws_bills = aws_get_bills_from_provider(aws_provider_uuid, self._schema, start_date, end_date)
        with schema_context(self._schema):
            aws_bill_ids = [str(bill.id) for bill in aws_bills]
            current_aws_bill_id = aws_bills.first().id if aws_bills else None
            current_ocp_report_period_id = report_period.id

        with CostModelDBAccessor(self._schema, aws_provider_uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = Decimal(markup.get("value", 0)) / 100

        # OpenShift on AWS
        with AWSReportDBAccessor(self._schema) as accessor:
            for start, end in date_range_pair(start_date, end_date, step=settings.TRINO_DATE_STEP):
                LOG.info(
                    "Updating OpenShift on AWS summary table for "
                    "\n\tSchema: %s \n\tProvider: %s \n\tDates: %s - %s"
                    "\n\tCluster ID: %s, AWS Bill ID: %s",
                    self._schema,
                    self._provider.uuid,
                    start,
                    end,
                    cluster_id,
                    current_aws_bill_id,
                )
                accessor.populate_ocp_on_aws_cost_daily_summary_presto(
                    start,
                    end,
                    openshift_provider_uuid,
                    aws_provider_uuid,
                    current_ocp_report_period_id,
                    current_aws_bill_id,
                    markup_value,
                )
            accessor.back_populate_ocp_on_aws_daily_summary(start_date, end_date, current_ocp_report_period_id)
            accessor.populate_ocp_on_aws_tags_summary_table(aws_bill_ids, start_date, end_date)

    def update_azure_summary_tables(self, openshift_provider_uuid, azure_provider_uuid, start_date, end_date):
        """Update operations specifically for OpenShift on Azure."""
        if isinstance(start_date, str):
            start_date = parser.parse(start_date).date()
        if isinstance(end_date, str):
            end_date = parser.parse(end_date).date()

        cluster_id = get_cluster_id_from_provider(openshift_provider_uuid)
        azure_bills = azure_get_bills_from_provider(azure_provider_uuid, self._schema, start_date, end_date)
        with schema_context(self._schema):
            azure_bill_ids = [str(bill.id) for bill in azure_bills]
            current_azure_bill_id = azure_bills.first().id if azure_bills else None

        with CostModelDBAccessor(self._schema, azure_provider_uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = Decimal(markup.get("value", 0)) / 100

        # OpenShift on Azure
        with AzureReportDBAccessor(self._schema) as accessor:
            for start, end in date_range_pair(start_date, end_date, step=settings.TRINO_DATE_STEP):
                LOG.info(
                    "Updating OpenShift on Azure summary table for "
                    "\n\tSchema: %s \n\tProvider: %s \n\tDates: %s - %s"
                    "\n\tCluster ID: %s, Azure Bill ID: %s",
                    self._schema,
                    self._provider.uuid,
                    start,
                    end,
                    cluster_id,
                    current_azure_bill_id,
                )
                accessor.populate_ocp_on_azure_cost_daily_summary_presto(
                    start,
                    end,
                    openshift_provider_uuid,
                    azure_provider_uuid,
                    cluster_id,
                    current_azure_bill_id,
                    markup_value,
                )
            accessor.populate_ocp_on_azure_tags_summary_table(azure_bill_ids, start_date, end_date)
