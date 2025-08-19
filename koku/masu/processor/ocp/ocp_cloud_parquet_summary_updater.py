#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Updates report summary tables in the database."""
import datetime
import logging

from dateutil import parser
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import schema_context

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from api.utils import get_months_in_date_range
from koku.pg_partition import PartitionHandlerMixin
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.ocp.ocp_cloud_updater_base import OCPCloudUpdaterBase
from masu.processor.ocp.ocp_cost_model_cost_updater import OCPCostModelCostUpdater
from masu.util.aws.common import get_bills_from_provider as aws_get_bills_from_provider
from masu.util.azure.common import get_bills_from_provider as azure_get_bills_from_provider
from masu.util.common import date_range_pair
from masu.util.gcp.common import get_bills_from_provider as gcp_get_bills_from_provider
from masu.util.ocp.common import get_cluster_alias_from_cluster_id
from masu.util.ocp.common import get_cluster_id_from_provider
from reporting.provider.aws.openshift.models import OCPAWSCostLineItemProjectDailySummaryP
from reporting.provider.aws.openshift.models import UI_SUMMARY_TABLES as OCPAWS_UI_SUMMARY_TABLES
from reporting.provider.azure.openshift.models import OCPAzureCostLineItemProjectDailySummaryP
from reporting.provider.azure.openshift.models import UI_SUMMARY_TABLES as OCPAZURE_UI_SUMMARY_TABLES
from reporting.provider.gcp.openshift.models import OCPGCPCostLineItemProjectDailySummaryP
from reporting.provider.gcp.openshift.models import UI_SUMMARY_TABLES as OCPGCP_UI_SUMMARY_TABLES

LOG = logging.getLogger(__name__)

TRUNCATE_TABLE = "truncate"
DELETE_TABLE = "delete"


class OCPCloudParquetReportSummaryUpdater(PartitionHandlerMixin, OCPCloudUpdaterBase):
    """Class to update OCP report summary data."""

    @property
    def provider_type(self):
        """Return the type of the provider used."""
        return self._provider.type

    @property
    def daily_summary_table(self):
        """Return the model class for the provider's OCP on Cloud daily summary table."""
        if self.provider_type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
            return OCPAWSCostLineItemProjectDailySummaryP
        elif self.provider_type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
            return OCPAzureCostLineItemProjectDailySummaryP
        elif self.provider_type in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
            return OCPGCPCostLineItemProjectDailySummaryP
        return None

    @property
    def ui_summary_tables(self):
        """Return the list of table names for UI summary."""
        if self.provider_type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
            return OCPAWS_UI_SUMMARY_TABLES
        elif self.provider_type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
            return OCPAZURE_UI_SUMMARY_TABLES
        elif self.provider_type in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
            return OCPGCP_UI_SUMMARY_TABLES
        return []

    @property
    def db_accessor(self):
        """Return the model class for the provider's OCP on Cloud daily summary table."""
        if self.provider_type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
            return AWSReportDBAccessor
        elif self.provider_type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
            return AzureReportDBAccessor
        elif self.provider_type in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
            return GCPReportDBAccessor
        return None

    def _can_truncate(self, start_date, end_date):
        """If summarizing a full month, we can TRUNCATE instead of DELETE"""
        dh = DateHelper()
        if isinstance(start_date, datetime.datetime):
            start_date = start_date.date()
        if isinstance(end_date, datetime.datetime):
            end_date = end_date.date()

        month_start = dh.month_start(start_date)
        month_end = dh.month_end(start_date)

        if start_date == month_start and end_date == month_end:
            # We do not want to TRUNCATE this table when multiple cloud sources contribute to the data
            infra_source_count = (
                Provider.objects.filter(
                    customer__schema_name=self._schema, infrastructure__infrastructure_type=self.provider_type
                )
                .values_list("infrastructure_id")
                .distinct()
                .count()
            )
            if infra_source_count < 2:
                return True

        return False

    def determine_truncates_and_deletes(self, start_date, end_date):
        """Clear out existing data in summary tables."""
        trunc_delete_map = {}
        if self._can_truncate(start_date, end_date):
            partition_str = f"_{start_date.strftime('%Y')}_{start_date.strftime('%m')}"
            trunc_delete_map[self.daily_summary_table.objects.model._meta.db_table + partition_str] = TRUNCATE_TABLE
            for table in self.ui_summary_tables:
                trunc_delete_map[table + partition_str] = TRUNCATE_TABLE
        else:
            trunc_delete_map[self.daily_summary_table.objects.model._meta.db_table] = DELETE_TABLE
            for table in self.ui_summary_tables:
                trunc_delete_map[table] = DELETE_TABLE

        return trunc_delete_map

    def delete_summary_table_data(self, start_date, end_date, table):
        """Clear out existing data in summary tables."""
        filters = {"source_uuid": str(self._provider.uuid)}
        dh = DateHelper()
        month_start = dh.month_start(start_date)
        with self.db_accessor(self._schema) as accessor:
            if table == self.daily_summary_table._meta.db_table:
                with schema_context(self._schema):
                    bills = accessor.bills_for_provider_uuid(self._provider.uuid, start_date=month_start)
                    current_bill_id = bills.first().id if bills else None
                filters = {
                    "cost_entry_bill_id": current_bill_id
                }  # Use cost_entry_bill_id to leverage DB index on DELETE
            accessor.delete_line_item_daily_summary_entries_for_date_range_raw(
                self._provider.uuid, start_date, end_date, table=table, filters=filters
            )

    def truncate_summary_table_data(self, partition_name):
        """Clear out existing data in summary tables by TRUNCATE."""
        with self.db_accessor(self._schema) as accessor:
            accessor.truncate_partition(partition_name)

    def update_summary_tables(self, start_date, end_date, ocp_provider_uuid, infra_provider_uuid, infra_provider_type):
        """Populate the summary tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.
            ocp_provider_uuid (str) The OpenShift source UUID.
            infra_tuple (tuple) A tuple of (Cloud provider source UUID, Source type)

        Returns
            None

        """
        if infra_provider_type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
            self.update_aws_summary_tables(ocp_provider_uuid, infra_provider_uuid, start_date, end_date)
        elif infra_provider_type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
            self.update_azure_summary_tables(ocp_provider_uuid, infra_provider_uuid, start_date, end_date)
        elif infra_provider_type in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
            self.update_gcp_summary_tables(ocp_provider_uuid, infra_provider_uuid, start_date, end_date)

        # Update markup for OpenShift tables
        provider = Provider.objects.get(uuid=ocp_provider_uuid)
        OCPCostModelCostUpdater(self._schema, provider)._update_markup_cost(start_date, end_date)

        # Update the UI tables for the OpenShift provider
        with OCPReportDBAccessor(self._schema) as ocp_accessor:
            ocp_accessor.populate_ui_summary_tables(start_date, end_date, ocp_provider_uuid)

    def update_aws_summary_tables(self, openshift_provider_uuid, aws_provider_uuid, start_date, end_date):
        """Update operations specifically for OpenShift on AWS."""
        if isinstance(start_date, str):
            start_date = parser.parse(start_date).date()
        if isinstance(end_date, str):
            end_date = parser.parse(end_date).date()

        cluster_id = get_cluster_id_from_provider(openshift_provider_uuid)
        cluster_alias = get_cluster_alias_from_cluster_id(cluster_id)

        with OCPReportDBAccessor(self._schema) as accessor:
            if not accessor.get_cluster_for_provider(openshift_provider_uuid):
                LOG.info(
                    log_json(
                        msg="cluster information not available - skipping OCP on Cloud summary table update for AWS",
                        provider_uuid=openshift_provider_uuid,
                        schema=self._schema,
                    )
                )
                return
            report_period = accessor.report_periods_for_provider_uuid(openshift_provider_uuid, start_date)
            if not report_period:
                LOG.info(
                    log_json(
                        msg="no report period for AWS provider",
                        provider_uuid=openshift_provider_uuid,
                        schema=self._schema,
                        start_date=start_date,
                    )
                )
                return

            accessor.delete_infrastructure_raw_cost_from_daily_summary(
                openshift_provider_uuid, report_period.id, start_date, end_date
            )
        aws_bills = aws_get_bills_from_provider(aws_provider_uuid, self._schema, start_date, end_date)
        if not aws_bills:
            # Without bill data, we cannot populate the summary table
            LOG.info(
                log_json(
                    msg="no AWS bill data found - skipping AWS summary table update",
                    schema_name=self._schema,
                    start_date=start_date,
                    end_date=end_date,
                    source_uuid=aws_provider_uuid,
                    cluster_id=cluster_id,
                )
            )
            return

        with schema_context(self._schema):
            self._handle_partitions(
                self._schema,
                (
                    "reporting_ocpawscostlineitem_daily_summary_p",
                    "reporting_ocpawscostlineitem_project_daily_summary_p",
                    "reporting_ocpaws_compute_summary_p",
                    "reporting_ocpaws_cost_summary_p",
                    "reporting_ocpaws_cost_summary_by_account_p",
                    "reporting_ocpaws_cost_summary_by_region_p",
                    "reporting_ocpaws_cost_summary_by_service_p",
                    "reporting_ocpaws_storage_summary_p",
                    "reporting_ocpaws_database_summary_p",
                    "reporting_ocpaws_network_summary_p",
                    "reporting_ocpallcostlineitem_daily_summary_p",
                    "reporting_ocpallcostlineitem_project_daily_summary_p",
                    "reporting_ocpall_compute_summary_pt",
                    "reporting_ocpall_cost_summary_pt",
                ),
                start_date,
                end_date,
            )

            aws_bill_ids = [bill.id for bill in aws_bills]
            current_aws_bill_id = aws_bill_ids[0]
            current_ocp_report_period_id = report_period.id
        # OpenShift on AWS
        sql_params = {
            "schema": self._schema,
            "start_date": start_date,
            "end_date": end_date,
            "source_uuid": aws_provider_uuid,
            "cluster_id": cluster_id,
            "cluster_alias": cluster_alias,
        }
        with self.db_accessor(self._schema) as accessor:
            context = accessor.extract_context_from_sql_params(sql_params)
            for start, end in date_range_pair(start_date, end_date, step=settings.TRINO_DATE_STEP):
                context["start_date"] = start
                context["end_date"] = end
                LOG.info(log_json(msg="updating OpenShift on AWS summary table", **context))
                accessor.populate_ocp_on_aws_cost_daily_summary_trino(
                    start,
                    end,
                    openshift_provider_uuid,
                    aws_provider_uuid,
                    current_ocp_report_period_id,
                    current_aws_bill_id,
                )
                sql_params["start_date"] = start
                sql_params["end_date"] = end
                accessor.back_populate_ocp_infrastructure_costs(start, end, current_ocp_report_period_id)
                accessor.populate_ocp_on_aws_tag_information(aws_bill_ids, start, end, current_ocp_report_period_id)
                accessor.populate_ocp_on_aws_ui_summary_tables_trino(
                    start, end, openshift_provider_uuid, aws_provider_uuid
                )

            with OCPReportDBAccessor(self._schema) as ocp_accessor:
                sql_params["source_type"] = "AWS"
                LOG.info(log_json(msg="processing OCP-ALL for AWS", **context))
                for start, end in date_range_pair(start_date, end_date, step=settings.TRINO_DATE_STEP):
                    sql_params["start_date"] = start
                    sql_params["end_date"] = end
                    ocp_accessor.populate_ocp_on_all_project_daily_summary("aws", sql_params)
                    ocp_accessor.populate_ocp_on_all_daily_summary("aws", sql_params)
                    ocp_accessor.populate_ocp_on_all_ui_summary_tables(sql_params)

        LOG.info(log_json(msg="updating ocp_on_cloud_updated_datetime OpenShift report periods", **context))
        with schema_context(self._schema):
            report_period.ocp_on_cloud_updated_datetime = timezone.now()
            report_period.save()

    def update_azure_summary_tables(self, openshift_provider_uuid, azure_provider_uuid, start_date, end_date):
        """Update operations specifically for OpenShift on Azure."""
        if isinstance(start_date, str):
            start_date = parser.parse(start_date).date()
        if isinstance(end_date, str):
            end_date = parser.parse(end_date).date()

        cluster_id = get_cluster_id_from_provider(openshift_provider_uuid)
        cluster_alias = get_cluster_alias_from_cluster_id(cluster_id)

        with OCPReportDBAccessor(self._schema) as accessor:
            if not accessor.get_cluster_for_provider(openshift_provider_uuid):
                LOG.info(
                    log_json(
                        msg="cluster information not available - skipping OCP on Cloud summary table update",
                        provider_uuid=openshift_provider_uuid,
                        schema=self._schema,
                    )
                )
                return
            report_period = accessor.report_periods_for_provider_uuid(openshift_provider_uuid, start_date)
            if not report_period:
                LOG.info(
                    log_json(
                        msg="no report period for Azure provider",
                        provider_uuid=openshift_provider_uuid,
                        start_date=start_date,
                        schema=self._schema,
                    )
                )
                return
            accessor.delete_infrastructure_raw_cost_from_daily_summary(
                openshift_provider_uuid, report_period.id, start_date, end_date
            )
        azure_bills = azure_get_bills_from_provider(azure_provider_uuid, self._schema, start_date, end_date)
        if not azure_bills:
            # Without bill data, we cannot populate the summary table
            LOG.info(
                log_json(
                    msg="no Azure bill data found - skipping Azure summary table update",
                    schema_name=self._schema,
                    start_date=start_date,
                    end_date=end_date,
                    source_uuid=azure_provider_uuid,
                    cluster_id=cluster_id,
                )
            )
            return
        with schema_context(self._schema):
            self._handle_partitions(
                self._schema,
                (
                    "reporting_ocpazurecostlineitem_daily_summary_p",
                    "reporting_ocpazurecostlineitem_project_daily_summary_p",
                    "reporting_ocpallcostlineitem_daily_summary_p",
                    "reporting_ocpallcostlineitem_project_daily_summary_p",
                    "reporting_ocpall_compute_summary_pt",
                    "reporting_ocpall_cost_summary_pt",
                    "reporting_ocpazure_cost_summary_p",
                    "reporting_ocpazure_cost_summary_by_account_p",
                    "reporting_ocpazure_cost_summary_by_location_p",
                    "reporting_ocpazure_cost_summary_by_service_p",
                    "reporting_ocpazure_compute_summary_p",
                    "reporting_ocpazure_storage_summary_p",
                    "reporting_ocpazure_network_summary_p",
                    "reporting_ocpazure_database_summary_p",
                ),
                start_date,
                end_date,
            )

            azure_bill_ids = [bill.id for bill in azure_bills]
            current_azure_bill_id = azure_bill_ids[0]
            current_ocp_report_period_id = report_period.id
        # OpenShift on Azure
        sql_params = {
            "schema": self._schema,
            "start_date": start_date,
            "end_date": end_date,
            "source_uuid": azure_provider_uuid,
            "cluster_id": cluster_id,
            "cluster_alias": cluster_alias,
        }
        with self.db_accessor(self._schema) as accessor:
            context = accessor.extract_context_from_sql_params(sql_params)
            for start, end in date_range_pair(start_date, end_date, step=settings.TRINO_DATE_STEP):
                context["start_date"] = start
                context["end_date"] = end
                LOG.info(
                    log_json(
                        msg="updating OpenShift on Azure summary table",
                        **context,
                    )
                )
                accessor.populate_ocp_on_azure_cost_daily_summary_trino(
                    start,
                    end,
                    openshift_provider_uuid,
                    azure_provider_uuid,
                    current_ocp_report_period_id,
                    current_azure_bill_id,
                )
                sql_params["start_date"] = start
                sql_params["end_date"] = end
                accessor.back_populate_ocp_infrastructure_costs(start, end, current_ocp_report_period_id)
                accessor.populate_ocp_on_azure_tag_information(
                    azure_bill_ids, start, end, current_ocp_report_period_id
                )
                accessor.populate_ocp_on_azure_ui_summary_tables_trino(
                    start, end, openshift_provider_uuid, azure_provider_uuid
                )

            with OCPReportDBAccessor(self._schema) as ocp_accessor:
                sql_params["source_type"] = "Azure"
                LOG.info(log_json(msg="processing OCP-ALL for Azure", **context))
                for start, end in date_range_pair(start_date, end_date, step=settings.TRINO_DATE_STEP):
                    sql_params["start_date"] = start
                    sql_params["end_date"] = end
                    ocp_accessor.populate_ocp_on_all_project_daily_summary("azure", sql_params)
                    ocp_accessor.populate_ocp_on_all_daily_summary("azure", sql_params)
                    ocp_accessor.populate_ocp_on_all_ui_summary_tables(sql_params)

        LOG.info(log_json(msg="updating ocp_on_cloud_updated_datetime OpenShift report periods", **context))
        with schema_context(self._schema):
            report_period.ocp_on_cloud_updated_datetime = timezone.now()
            report_period.save()

    def update_gcp_summary_tables(self, openshift_provider_uuid, gcp_provider_uuid, start_date, end_date):
        """Update operations specifically for OpenShift on GCP."""
        if isinstance(start_date, str):
            start_date = parser.parse(start_date).date()
        if isinstance(end_date, str):
            end_date = parser.parse(end_date).date()

        cluster_id = get_cluster_id_from_provider(openshift_provider_uuid)
        cluster_alias = get_cluster_alias_from_cluster_id(cluster_id)

        # This needs to run per billing month because OCP data is billing period locked and GCP has cross billing data
        months = get_months_in_date_range(start=start_date, end=end_date)
        for month in months:
            with OCPReportDBAccessor(self._schema) as accessor:
                report_period = accessor.report_periods_for_provider_uuid(openshift_provider_uuid, month[0])
                if not report_period:
                    LOG.info(
                        log_json(
                            msg="no report period for GCP provider",
                            provider_uuid=openshift_provider_uuid,
                            start_date=month[0],
                            schema=self._schema,
                        )
                    )
                    return
                accessor.delete_infrastructure_raw_cost_from_daily_summary(
                    openshift_provider_uuid, report_period.id, month[0], month[1]
                )

            gcp_bills = gcp_get_bills_from_provider(gcp_provider_uuid, self._schema, month[0], month[1])
            if not gcp_bills:
                # Without bill data, we cannot populate the summary table
                LOG.info(
                    log_json(
                        msg="no GCP bill data found - skipping GCP summary table update",
                        schema_name=self._schema,
                        start_date=month[0],
                        end_date=month[1],
                        source_uuid=gcp_provider_uuid,
                        cluster_id=cluster_id,
                    )
                )
                return
            with schema_context(self._schema):
                self._handle_partitions(
                    self._schema,
                    (
                        (
                            "reporting_ocpgcpcostlineitem_daily_summary_p",
                            "reporting_ocpgcpcostlineitem_project_daily_summary_p",
                            "reporting_ocpallcostlineitem_daily_summary_p",
                            "reporting_ocpallcostlineitem_project_daily_summary_p",
                            "reporting_ocpall_compute_summary_pt",
                            "reporting_ocpall_cost_summary_pt",
                        )
                        + OCPGCP_UI_SUMMARY_TABLES
                    ),
                    month[0],
                    month[1],
                )

                gcp_bill_ids = [bill.id for bill in gcp_bills]
                current_gcp_bill_id = gcp_bill_ids[0]
                current_ocp_report_period_id = report_period.id
            # OpenShift on GCP
            sql_params = {
                "schema": self._schema,
                "start_date": month[0],
                "end_date": month[1],
                "source_uuid": gcp_provider_uuid,
                "cluster_id": cluster_id,
                "cluster_alias": cluster_alias,
            }

            with self.db_accessor(self._schema) as accessor:
                context = accessor.extract_context_from_sql_params(sql_params)
                for start, end in date_range_pair(month[0], month[1], step=settings.TRINO_DATE_STEP):
                    context["start_date"] = start
                    context["end_date"] = end
                    LOG.info(log_json(msg="updating OpenShift on GCP summary table", **context))
                    accessor.populate_ocp_on_gcp_cost_daily_summary_trino(
                        start,
                        end,
                        openshift_provider_uuid,
                        gcp_provider_uuid,
                        current_ocp_report_period_id,
                        current_gcp_bill_id,
                    )
                    sql_params["start_date"] = start
                    sql_params["end_date"] = end
                    accessor.back_populate_ocp_infrastructure_costs(start, end, current_ocp_report_period_id)
                    accessor.populate_ocp_on_gcp_ui_summary_tables_trino(
                        start, end, openshift_provider_uuid, gcp_provider_uuid
                    )
                    accessor.populate_ocp_on_gcp_tag_information(gcp_bill_ids, start, end, current_ocp_report_period_id)

                with OCPReportDBAccessor(self._schema) as ocp_accessor:
                    sql_params["source_type"] = "GCP"
                    context = ocp_accessor.extract_context_from_sql_params(sql_params)
                    LOG.info(log_json(msg="processing OCP-ALL for GCP (T)", **context))
                    for start, end in date_range_pair(month[0], month[1], step=settings.TRINO_DATE_STEP):
                        sql_params["start_date"] = start
                        sql_params["end_date"] = end
                        ocp_accessor.populate_ocp_on_all_project_daily_summary("gcp", sql_params)
                        ocp_accessor.populate_ocp_on_all_daily_summary("gcp", sql_params)
                        ocp_accessor.populate_ocp_on_all_ui_summary_tables(sql_params)

            LOG.info(
                log_json(
                    msg="updating ocp_on_cloud_updated_datetime on OpenShift report periods",
                    schema=self._schema,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
            with schema_context(self._schema):
                report_period.ocp_on_cloud_updated_datetime = timezone.now()
                report_period.save()
