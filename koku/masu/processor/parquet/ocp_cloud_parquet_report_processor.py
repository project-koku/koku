#
# Copyright 2021 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Processor to filter cost data for OpenShift and store as parquet."""
import logging
from functools import cached_property

from tenant_schemas.utils import schema_context

from api.provider.models import Provider
from api.utils import DateHelper
from masu.config import Config
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor.ocp.ocp_cloud_updater_base import OCPCloudUpdaterBase
from masu.processor.parquet.parquet_report_processor import PARQUET_EXT
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessor
from masu.util.aws.common import match_openshift_resources_and_labels
from masu.util.common import get_path_prefix


LOG = logging.getLogger(__name__)
REPORT_TYPE = "openshift"


class OCPCloudParquetReportProcessor(ParquetReportProcessor):
    """Parquet report processor for OCP on Cloud infrastructure data."""

    @property
    def parquet_ocp_on_cloud_path_s3(self):
        """The path in the S3 bucket where Parquet files are loaded."""
        return get_path_prefix(
            self.account,
            self.provider_type,
            self.provider_uuid,
            self.start_date,
            Config.PARQUET_DATA_TYPE,
            report_type=REPORT_TYPE,
            daily=True,
        )

    @property
    def report_type(self):
        """Report OCP on Cloud report type."""
        return REPORT_TYPE

    @property
    def ocp_on_cloud_data_processor(self):
        """Post processor based on provider type."""
        ocp_on_cloud_data_processor = None
        if self.provider_type == Provider.PROVIDER_AWS:
            ocp_on_cloud_data_processor = match_openshift_resources_and_labels

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
        infra_map = updater.get_infra_map()
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
        return None

    @cached_property
    def bill_id(self):
        """Return the bill ID from the infrastructure provider."""
        bill_id = None
        with schema_context(self.schema_name):
            bills = self.db_accessor.bills_for_provider_uuid(self.provider_uuid, self.start_date)
            bill_id = bills.first().id if bills else None
        return bill_id

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

    def create_ocp_on_cloud_parquet(self, data_frame, ocp_provider_uuid):
        """Create a parquet file for daily aggregated data."""
        file_name = f"{ocp_provider_uuid}{PARQUET_EXT}"
        file_path = f"{self.local_path}/{file_name}"
        self._write_parquet_to_file(file_path, file_name, data_frame, file_type=self.report_type)
        self.create_parquet_table(file_path, daily=True)

    def process(self, parquet_base_filename, daily_data_frame):
        """Filter data and convert to parquet."""
        for ocp_provider_uuid, infra_tuple in self.ocp_infrastructure_map.items():
            infra_provider_uuid = infra_tuple[0]
            if infra_provider_uuid != self.provider_uuid:
                continue
            msg = (
                f"Processing OpenShift on {self.provider_type} to parquet."
                f"\n\tStart date: {str(self.start_date)}\n\tFile: {str(self.report_file)}"
            )
            LOG.info(msg)
            # Get OpenShift topology data
            with OCPReportDBAccessor(self.schema_name) as accessor:
                cluster_topology = accessor.get_openshift_topology_for_provider(ocp_provider_uuid)
            # Get matching tags
            report_period_id = self.get_report_period_id(ocp_provider_uuid)
            matched_tags = self.db_accessor.get_openshift_on_cloud_matched_tags(self.bill_id, report_period_id)
            if not matched_tags:
                matched_tags = self.db_accessor.get_openshift_on_cloud_matched_tags_trino(
                    self.provider_uuid, ocp_provider_uuid, self.start_date, self.end_date
                )
            LOG.info(matched_tags)
            openshift_filtered_data_frame = self.ocp_on_cloud_data_processor(
                daily_data_frame, cluster_topology, matched_tags
            )

            self.create_ocp_on_cloud_parquet(openshift_filtered_data_frame, ocp_provider_uuid)
