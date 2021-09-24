#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Updates report summary tables in the database."""
import datetime
import logging
from decimal import Decimal

from dateutil import parser
from dateutil.relativedelta import relativedelta
from tenant_schemas.utils import schema_context

from api.provider.models import Provider
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.processor.ocp.ocp_cloud_updater_base import OCPCloudUpdaterBase
from masu.processor.ocp.ocp_cost_model_cost_updater import OCPCostModelCostUpdater
from masu.util.aws.common import get_bills_from_provider as aws_get_bills_from_provider
from masu.util.azure.common import get_bills_from_provider as azure_get_bills_from_provider
from masu.util.common import date_range_pair
from masu.util.ocp.common import get_cluster_alias_from_cluster_id
from masu.util.ocp.common import get_cluster_id_from_provider
from reporting.models import PartitionedTable


LOG = logging.getLogger(__name__)


class OCPCloudReportSummaryUpdater(OCPCloudUpdaterBase):
    """Class to update OCP report summary data."""

    def update_summary_tables(self, start_date, end_date):
        """Populate the summary tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            None

        """
        infra_map = self.get_infra_map()
        openshift_provider_uuids, infra_provider_uuids = self.get_openshift_and_infra_providers_lists(infra_map)

        if self._provider.type == Provider.PROVIDER_OCP and self._provider_uuid not in openshift_provider_uuids:
            infra_map = self._generate_ocp_infra_map_from_sql(start_date, end_date)
        elif self._provider.type in Provider.CLOUD_PROVIDER_LIST and self._provider_uuid not in infra_provider_uuids:
            # When running for an Infrastructure provider we want all
            # of the matching clusters to run
            infra_map = self._generate_ocp_infra_map_from_sql(start_date, end_date)

        # If running as an infrastructure provider (e.g. AWS)
        # this loop should run for all associated OpenShift clusters.
        # If running for an OpenShift provider, it should just run one time.
        for ocp_provider_uuid, infra_tuple in infra_map.items():
            infra_provider_uuid = infra_tuple[0]
            infra_provider_type = infra_tuple[1]
            if infra_provider_type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
                self.update_aws_summary_tables(ocp_provider_uuid, infra_provider_uuid, start_date, end_date)
            elif infra_provider_type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
                self.update_azure_summary_tables(ocp_provider_uuid, infra_provider_uuid, start_date, end_date)

            # Update markup for OpenShift tables
            with ProviderDBAccessor(ocp_provider_uuid) as provider_accessor:
                OCPCostModelCostUpdater(self._schema, provider_accessor.provider)._update_markup_cost(
                    start_date, end_date
                )

    def _handle_partitions(self, table_names, start_date, end_date):
        if isinstance(start_date, datetime.datetime):
            start_date = start_date.date()
        if isinstance(end_date, datetime.datetime):
            end_date = end_date.date()
        if isinstance(table_names, str):
            table_names = [table_names]

        for table_name in table_names:
            tmplpart = PartitionedTable.objects.filter(
                schema_name=self._schema, partition_of_table_name=table_name, partition_type=PartitionedTable.RANGE
            ).first()
            if tmplpart:
                partition_start = start_date.replace(day=1)
                month_interval = relativedelta(months=1)
                needed_partition = None
                partition_col = tmplpart.partition_col
                newpart_vals = dict(
                    schema_name=self._schema,
                    table_name=None,
                    partition_of_table_name=table_name,
                    partition_type=PartitionedTable.RANGE,
                    partition_col=partition_col,
                    partition_parameters={"default": False, "from": None, "to": None},
                    active=True,
                )
                for _ in range(relativedelta(end_date.replace(day=1), partition_start).months + 1):
                    if needed_partition is None:
                        needed_partition = partition_start
                    else:
                        needed_partition = needed_partition + month_interval

                    partition_name = f"{table_name}_{needed_partition.strftime('%Y_%m')}"
                    newpart_vals["table_name"] = partition_name
                    newpart_vals["partition_parameters"]["from"] = str(needed_partition)
                    newpart_vals["partition_parameters"]["to"] = str(needed_partition + month_interval)
                    # Successfully creating a new record will also create the partition
                    newpart, created = PartitionedTable.objects.get_or_create(
                        defaults=newpart_vals,
                        schema_name=self._schema,
                        partition_of_table_name=table_name,
                        table_name=partition_name,
                    )
                    LOG.debug(f"part = {newpart}")
                    LOG.debug(f"ctd = {created}")
                    if created:
                        LOG.info(f"Created partition {newpart.schema_name}.{newpart.table_name}")

    def update_aws_summary_tables(self, openshift_provider_uuid, aws_provider_uuid, start_date, end_date):
        """Update operations specifically for OpenShift on AWS."""
        if isinstance(start_date, str):
            start_date = parser.parse(start_date)
        if isinstance(end_date, str):
            end_date = parser.parse(end_date)

        with schema_context(self._schema):
            self._handle_partitions(
                (
                    "reporting_ocpawscostlineitem_daily_summary",
                    "reporting_ocpawscostlineitem_project_daily_summary",
                    "reporting_ocpallcostlineitem_daily_summary_p",
                    "reporting_ocpallcostlineitem_project_daily_summary_p",
                ),
                start_date,
                end_date,
            )

        cluster_id = get_cluster_id_from_provider(openshift_provider_uuid)
        cluster_alias = get_cluster_alias_from_cluster_id(cluster_id)
        aws_bills = aws_get_bills_from_provider(aws_provider_uuid, self._schema, start_date, end_date)

        with schema_context(self._schema):
            aws_bill_ids = []
            aws_bill_ids = [str(bill.id) for bill in aws_bills]

        with CostModelDBAccessor(self._schema, aws_provider_uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = Decimal(markup.get("value", 0)) / 100

        # OpenShift on AWS
        with AWSReportDBAccessor(self._schema) as accessor:
            for start, end in date_range_pair(start_date, end_date):
                LOG.info(
                    "Updating OpenShift on AWS summary table for "
                    "\n\tSchema: %s \n\tProvider: %s \n\tDates: %s - %s"
                    "\n\tCluster ID: %s, AWS Bill IDs: %s",
                    self._schema,
                    self._provider.uuid,
                    start,
                    end,
                    cluster_id,
                    str(aws_bill_ids),
                )
                accessor.populate_ocp_on_aws_cost_daily_summary(start, end, cluster_id, aws_bill_ids, markup_value)
            accessor.populate_ocp_on_aws_tags_summary_table(aws_bill_ids, start_date, end_date)

        with OCPReportDBAccessor(self._schema) as ocp_accessor:
            sql_params = {
                "start_date": start_date,
                "end_date": end_date,
                "source_uuid": self._provider.uuid,
                "cluster_id": cluster_id,
                "cluster_alias": cluster_alias,
            }
            LOG.info(f"Processing OCP-ALL for AWS  (s={start_date} e={end_date})")
            ocp_accessor.populate_ocp_on_all_project_daily_summary("aws", sql_params)
            ocp_accessor.populate_ocp_on_all_daily_summary("aws", sql_params)

    def update_azure_summary_tables(self, openshift_provider_uuid, azure_provider_uuid, start_date, end_date):
        """Update operations specifically for OpenShift on Azure."""
        if isinstance(start_date, str):
            start_date = parser.parse(start_date)
        if isinstance(end_date, str):
            end_date = parser.parse(end_date)

        with schema_context(self._schema):
            self._handle_partitions(
                (
                    "reporting_ocpazurecostlineitem_daily_summary",
                    "reporting_ocpazurecostlineitem_project_daily_summary",
                    "reporting_ocpallcostlineitem_daily_summary_p",
                    "reporting_ocpallcostlineitem_project_daily_summary_p",
                ),
                start_date,
                end_date,
            )

        cluster_id = get_cluster_id_from_provider(openshift_provider_uuid)
        cluster_alias = get_cluster_alias_from_cluster_id(cluster_id)
        azure_bills = azure_get_bills_from_provider(azure_provider_uuid, self._schema, start_date, end_date)

        with schema_context(self._schema):
            azure_bill_ids = []
            azure_bill_ids = [str(bill.id) for bill in azure_bills]

        with CostModelDBAccessor(self._schema, azure_provider_uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = Decimal(markup.get("value", 0)) / 100

        # OpenShift on Azure
        with AzureReportDBAccessor(self._schema) as accessor:
            for start, end in date_range_pair(start_date, end_date):
                LOG.info(
                    "Updating OpenShift on Azure summary table for "
                    "\n\tSchema: %s \n\tProvider: %s \n\tDates: %s - %s"
                    "\n\tCluster ID: %s, Azure Bill IDs: %s",
                    self._schema,
                    self._provider.uuid,
                    start,
                    end,
                    cluster_id,
                    str(azure_bill_ids),
                )
                accessor.populate_ocp_on_azure_cost_daily_summary(start, end, cluster_id, azure_bill_ids, markup_value)
            accessor.populate_ocp_on_azure_tags_summary_table(azure_bill_ids, start_date, end_date)

        with OCPReportDBAccessor(self._schema) as ocp_accessor:
            sql_params = {
                "start_date": start_date,
                "end_date": end_date,
                "source_uuid": self._provider.uuid,
                "cluster_id": cluster_id,
                "cluster_alias": cluster_alias,
            }
            LOG.info(f"Processing OCP-ALL for Azure (s={start_date} e={end_date})")
            ocp_accessor.populate_ocp_on_all_project_daily_summary("azure", sql_params)
            ocp_accessor.populate_ocp_on_all_daily_summary("azure", sql_params)
