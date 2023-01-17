#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
#
"""Processor to filter cost data for OpenShift and store as parquet."""
import logging
from functools import cached_property

from tenant_schemas.utils import schema_context

from api.provider.models import Provider
from api.utils import DateHelper
from koku.cache import get_cached_matching_tags
from koku.cache import set_cached_matching_tags
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor.ocp.ocp_cloud_updater_base import OCPCloudUpdaterBase
from masu.processor.parquet.parquet_report_processor import OPENSHIFT_REPORT_TYPE
from masu.processor.parquet.parquet_report_processor import PARQUET_EXT
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessor
from masu.util.aws.common import match_openshift_resources_and_labels as aws_match_openshift_resources_and_labels
from masu.util.azure.common import match_openshift_resources_and_labels as azure_match_openshift_resources_and_labels
from masu.util.gcp.common import match_openshift_resources_and_labels as gcp_match_openshift_resources_and_labels
from reporting.provider.ocp.models import OCPEnabledTagKeys

LOG = logging.getLogger(__name__)


class OCPCloudParquetReportProcessor(ParquetReportProcessor):
    """Parquet report processor for OCP on Cloud infrastructure data."""

    @property
    def report_type(self):
        """Report OCP on Cloud report type."""
        return OPENSHIFT_REPORT_TYPE

    @property
    def ocp_on_cloud_data_processor(self):
        """Post processor based on provider type."""
        ocp_on_cloud_data_processor = None
        if self.provider_type == Provider.PROVIDER_AWS:
            ocp_on_cloud_data_processor = aws_match_openshift_resources_and_labels
        elif self.provider_type == Provider.PROVIDER_AZURE:
            ocp_on_cloud_data_processor = azure_match_openshift_resources_and_labels
        elif self.provider_type == Provider.PROVIDER_GCP:
            ocp_on_cloud_data_processor = gcp_match_openshift_resources_and_labels

        return ocp_on_cloud_data_processor

    @property
    def end_date(self):
        """Return an end date."""
        dh = DateHelper()
        return dh.month_end(self.start_date)

    @cached_property
    def ocp_infrastructure_map(self):
        provider = Provider.objects.get(uuid=self.provider_uuid)
        manifest_accessor = ReportManifestDBAccessor()
        manifest = manifest_accessor.get_manifest_by_id(self.manifest_id)

        updater = OCPCloudUpdaterBase(self.schema_name, provider, manifest)
        infra_map = updater.get_infra_map_from_providers()
        openshift_provider_uuids, infra_provider_uuids = updater.get_openshift_and_infra_providers_lists(infra_map)

        if self.provider_type in Provider.CLOUD_PROVIDER_LIST and self.provider_uuid not in infra_provider_uuids:
            # When running for an Infrastructure provider we want all
            # of the matching clusters to run
            infra_map = updater._generate_ocp_infra_map_from_sql_trino(self.start_date, self.end_date)

        return infra_map

    @property
    def db_accessor(self):
        """Return the accessor for the infrastructure provider."""
        if self.provider_type == Provider.PROVIDER_AWS:
            return AWSReportDBAccessor(self.schema_name)
        elif self.provider_type == Provider.PROVIDER_AZURE:
            return AzureReportDBAccessor(self.schema_name)
        elif self.provider_type == Provider.PROVIDER_GCP:
            return GCPReportDBAccessor(self.schema_name)
        return None

    @cached_property
    def bill_id(self):
        """Return the bill ID from the infrastructure provider."""
        bill_id = None
        with schema_context(self.schema_name):
            bills = self.db_accessor.bills_for_provider_uuid(self.provider_uuid, self.start_date)
            bill_id = bills.first().id if bills else None
        return bill_id

    @cached_property
    def has_enabled_ocp_labels(self):
        """Return whether we have enabled OCP labels."""
        with schema_context(self.schema_name):
            return OCPEnabledTagKeys.objects.exists()

    def get_report_period_id(self, ocp_provider_uuid):
        """Return the OpenShift report period ID."""
        report_period_id = None
        with OCPReportDBAccessor(self.schema_name) as accessor:
            with schema_context(self.schema_name):
                report_period = accessor.report_periods_for_provider_uuid(ocp_provider_uuid, self.start_date)
                report_period_id = report_period.id if report_period else None
        return report_period_id

    def _determin_s3_path(self, file_type):
        """Determine the s3 path to use to write a parquet file to."""
        if file_type == self.report_type:
            return self.parquet_ocp_on_cloud_path_s3
        return None

    def create_ocp_on_cloud_parquet(self, data_frame, parquet_base_filename, file_number):
        """Create a parquet file for daily aggregated data."""
        # Add the OCP UUID in case multiple clusters are running on this cloud source.
        if self._provider_type == Provider.PROVIDER_GCP:
            if data_frame.first_valid_index() is not None:
                parquet_base_filename = (
                    f"{data_frame['invoice_month'].values[0]}{parquet_base_filename[parquet_base_filename.find('_'):]}"
                )
        file_name = f"{parquet_base_filename}_{file_number}_{PARQUET_EXT}"
        file_path = f"{self.local_path}/{file_name}"
        self._write_parquet_to_file(file_path, file_name, data_frame, file_type=self.report_type)
        self.create_parquet_table(file_path, daily=True)

    def get_matched_tags(self, ocp_provider_uuids):
        """Get tags that match between OCP and the cloud source."""
        # Get matching tags
        matched_tags = get_cached_matching_tags(self.schema_name, self.provider_type)
        if matched_tags:
            LOG.info("Retreived matching tags from cache.")
            return matched_tags
        if self.has_enabled_ocp_labels:
            enabled_tags = self.db_accessor.check_for_matching_enabled_keys()
            if enabled_tags:
                LOG.info("Getting matching tags from Postgres.")
                matched_tags = self.db_accessor.get_openshift_on_cloud_matched_tags(self.bill_id)
            if not matched_tags and enabled_tags:
                LOG.info("Matched tags not yet available via Postgres. Getting matching tags from Trino.")
                if self._provider_type in [Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL]:
                    matched_tags = self.db_accessor.get_openshift_on_cloud_matched_tags_trino(
                        self.provider_uuid,
                        ocp_provider_uuids,
                        self.start_date,
                        self.end_date,
                        self.invoice_month_date,
                    )
                else:
                    matched_tags = self.db_accessor.get_openshift_on_cloud_matched_tags_trino(
                        self.provider_uuid, tuple(ocp_provider_uuids), self.start_date, self.end_date
                    )
        set_cached_matching_tags(self.schema_name, self.provider_type, matched_tags)
        return matched_tags

    def process(self, parquet_base_filename, daily_data_frames):
        """Filter data and convert to parquet."""
        ocp_provider_uuids = []
        for ocp_provider_uuid, infra_tuple in self.ocp_infrastructure_map.items():
            infra_provider_uuid = infra_tuple[0]
            if infra_provider_uuid != self.provider_uuid:
                continue
            msg = (
                f"Processing OpenShift on {self.provider_type} to parquet for Openshift source {ocp_provider_uuid}"
                f"\n\tStart date: {str(self.start_date)}\n\tFile: {str(self.report_file)}"
            )
            LOG.info(msg)
            with OCPReportDBAccessor(self.schema_name) as accessor:
                if not accessor.get_cluster_for_provider(ocp_provider_uuid):
                    LOG.info(
                        f"No cluster information available for OCP Provider: {ocp_provider_uuid},"
                        + "skipping OCP on Cloud parquet processing."
                    )
                    continue
                ocp_provider_uuids.append(ocp_provider_uuid)
        # # Get OpenShift topology data
        if ocp_provider_uuids != []:
            with OCPReportDBAccessor(self.schema_name) as accessor:
                cluster_topology = accessor.get_openshift_topology_for_multiple_providers(ocp_provider_uuids)
                matched_tags = self.get_matched_tags(ocp_provider_uuids)
                for i, daily_data_frame in enumerate(daily_data_frames):
                    openshift_filtered_data_frame = self.ocp_on_cloud_data_processor(
                        daily_data_frame, cluster_topology, matched_tags
                    )

                    self.create_ocp_on_cloud_parquet(openshift_filtered_data_frame, parquet_base_filename, i)
