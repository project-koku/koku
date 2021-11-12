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
from masu.util.ocp.common import get_cluster_alias_from_cluster_id
from masu.util.ocp.common import get_cluster_id_from_provider
from reporting.provider.aws.openshift.models import OCPAWSCostLineItemProjectDailySummary
from reporting.provider.azure.openshift.models import OCPAzureCostLineItemProjectDailySummary
from reporting.provider.ocp.models import UI_SUMMARY_TABLES_MARKUP_SUBSET

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
        cluster_alias = get_cluster_alias_from_cluster_id(cluster_id)

        with OCPReportDBAccessor(self._schema) as accessor:
            report_period = accessor.report_periods_for_provider_uuid(openshift_provider_uuid, start_date)
            accessor.delete_infrastructure_raw_cost_from_daily_summary(
                openshift_provider_uuid, report_period.id, start_date, end_date
            )
        aws_bills = aws_get_bills_from_provider(aws_provider_uuid, self._schema, start_date, end_date)
        with schema_context(self._schema):
            self._handle_partitions(
                self._schema,
                (
                    "reporting_ocpawscostlineitem_daily_summary",
                    "reporting_ocpawscostlineitem_project_daily_summary",
                    "reporting_ocpallcostlineitem_daily_summary_p",
                    "reporting_ocpallcostlineitem_project_daily_summary_p",
                    "reporting_ocpall_compute_summary_pt",
                    "reporting_ocpall_cost_summary_pt",
                ),
                start_date,
                end_date,
            )

            aws_bill_ids = [str(bill.id) for bill in aws_bills]
            current_aws_bill_id = aws_bills.first().id if aws_bills else None
            current_ocp_report_period_id = report_period.id

        with CostModelDBAccessor(self._schema, aws_provider_uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = Decimal(markup.get("value", 0)) / 100

        with CostModelDBAccessor(self._schema, openshift_provider_uuid) as cost_model_accessor:
            distribution = cost_model_accessor.distribution

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
                accessor.delete_line_item_daily_summary_entries_for_date_range(
                    self._provider.uuid, start, end, table=OCPAWSCostLineItemProjectDailySummary
                )
                accessor.populate_ocp_on_aws_cost_daily_summary_presto(
                    start,
                    end,
                    openshift_provider_uuid,
                    aws_provider_uuid,
                    current_ocp_report_period_id,
                    current_aws_bill_id,
                    markup_value,
                    distribution,
                )
            accessor.back_populate_ocp_on_aws_daily_summary(start_date, end_date, current_ocp_report_period_id)
            accessor.populate_ocp_on_aws_tags_summary_table(aws_bill_ids, start_date, end_date)

            with OCPReportDBAccessor(self._schema) as ocp_accessor:
                sql_params = {
                    "schema_name": self._schema,
                    "start_date": start_date,
                    "end_date": end_date,
                    "source_uuid": self._provider.uuid,
                    "cluster_id": cluster_id,
                    "cluster_alias": cluster_alias,
                    "source_type": "AWS",
                }
                LOG.info(f"Processing OCP-ALL for AWS (T)  (s={start_date} e={end_date})")
                ocp_accessor.populate_ocp_on_all_project_daily_summary("aws", sql_params)
                ocp_accessor.populate_ocp_on_all_daily_summary("aws", sql_params)
                ocp_accessor.populate_ocp_on_all_ui_summary_tables(sql_params)

                ocp_accessor.populate_ui_summary_tables(
                    start, end, openshift_provider_uuid, UI_SUMMARY_TABLES_MARKUP_SUBSET
                )

    def update_azure_summary_tables(self, openshift_provider_uuid, azure_provider_uuid, start_date, end_date):
        """Update operations specifically for OpenShift on Azure."""
        if isinstance(start_date, str):
            start_date = parser.parse(start_date).date()
        if isinstance(end_date, str):
            end_date = parser.parse(end_date).date()

        cluster_id = get_cluster_id_from_provider(openshift_provider_uuid)
        cluster_alias = get_cluster_alias_from_cluster_id(cluster_id)

        with OCPReportDBAccessor(self._schema) as accessor:
            report_period = accessor.report_periods_for_provider_uuid(openshift_provider_uuid, start_date)
            accessor.delete_infrastructure_raw_cost_from_daily_summary(
                openshift_provider_uuid, report_period.id, start_date, end_date
            )
        azure_bills = azure_get_bills_from_provider(azure_provider_uuid, self._schema, start_date, end_date)
        with schema_context(self._schema):
            self._handle_partitions(
                self._schema,
                (
                    "reporting_ocpazurecostlineitem_daily_summary",
                    "reporting_ocpazurecostlineitem_project_daily_summary",
                    "reporting_ocpallcostlineitem_daily_summary_p",
                    "reporting_ocpallcostlineitem_project_daily_summary_p",
                    "reporting_ocpall_compute_summary_pt",
                    "reporting_ocpall_cost_summary_pt",
                ),
                start_date,
                end_date,
            )

            azure_bill_ids = [str(bill.id) for bill in azure_bills]
            current_azure_bill_id = azure_bills.first().id if azure_bills else None
            current_ocp_report_period_id = report_period.id

        with CostModelDBAccessor(self._schema, azure_provider_uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = Decimal(markup.get("value", 0)) / 100

        with CostModelDBAccessor(self._schema, openshift_provider_uuid) as cost_model_accessor:
            distribution = cost_model_accessor.distribution

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
                accessor.delete_line_item_daily_summary_entries_for_date_range(
                    self._provider.uuid, start, end, table=OCPAzureCostLineItemProjectDailySummary
                )
                accessor.populate_ocp_on_azure_cost_daily_summary_presto(
                    start,
                    end,
                    openshift_provider_uuid,
                    azure_provider_uuid,
                    current_ocp_report_period_id,
                    current_azure_bill_id,
                    markup_value,
                    distribution,
                )
            accessor.back_populate_ocp_on_azure_daily_summary(start_date, end_date, current_ocp_report_period_id)
            accessor.populate_ocp_on_azure_tags_summary_table(azure_bill_ids, start_date, end_date)

            with OCPReportDBAccessor(self._schema) as ocp_accessor:
                sql_params = {
                    "schema_name": self._schema,
                    "start_date": start_date,
                    "end_date": end_date,
                    "source_uuid": self._provider.uuid,
                    "cluster_id": cluster_id,
                    "cluster_alias": cluster_alias,
                    "source_type": "Azure",
                }
                LOG.info(f"Processing OCP-ALL for Azure (T)  (s={start_date} e={end_date})")
                ocp_accessor.populate_ocp_on_all_project_daily_summary("azure", sql_params)
                ocp_accessor.populate_ocp_on_all_daily_summary("azure", sql_params)
                ocp_accessor.populate_ocp_on_all_ui_summary_tables(sql_params)

                ocp_accessor.populate_ui_summary_tables(
                    start, end, openshift_provider_uuid, UI_SUMMARY_TABLES_MARKUP_SUBSET
                )
