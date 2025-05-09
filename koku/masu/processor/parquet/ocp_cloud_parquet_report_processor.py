#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
#
"""Processor to filter cost data for OpenShift and store as parquet."""
import json
import logging
import pkgutil
from functools import cached_property

import pandas as pd
from django_tenants.utils import schema_context

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from koku.cache import build_matching_tags_key
from koku.cache import get_value_from_cache
from koku.cache import is_key_in_cache
from koku.cache import set_value_in_cache
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor import is_tag_processing_disabled
from masu.processor.ocp.ocp_cloud_updater_base import OCPCloudUpdaterBase
from masu.processor.parquet.parquet_report_processor import OPENSHIFT_REPORT_TYPE
from masu.processor.parquet.parquet_report_processor import PARQUET_EXT
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessor
from masu.processor.parquet.summary_sql_metadata import SummarySqlMetadata
from masu.util.aws.common import match_openshift_resources_and_labels as aws_match_openshift_resources_and_labels
from masu.util.azure.common import match_openshift_resources_and_labels as azure_match_openshift_resources_and_labels
from masu.util.gcp.common import match_openshift_resources_and_labels as gcp_match_openshift_resources_and_labels
from reporting.provider.all.models import EnabledTagKeys
from reporting_common.models import CombinedChoices

LOG = logging.getLogger(__name__)

GCP_PARTITION_MAP = {
    "source": "varchar",
    "year": "varchar",
    "month": "varchar",
    "day": "varchar",
}


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

    @property
    def partition_map(self):
        """Partition Map based on provider type."""
        if self.provider_type in {Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL}:
            return GCP_PARTITION_MAP
        return None

    @cached_property
    def ocp_infrastructure_map(self):
        provider = Provider.objects.get(uuid=self.provider_uuid)
        manifest_accessor = ReportManifestDBAccessor()
        manifest = manifest_accessor.get_manifest_by_id(self.manifest_id)

        updater = OCPCloudUpdaterBase(self.schema_name, provider, manifest)
        infra_map = updater.get_infra_map_from_providers()

        if self.provider_type in Provider.CLOUD_PROVIDER_LIST:
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
            return EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP).exists()

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

    def create_ocp_on_cloud_parquet(self, data_frame, parquet_base_filename):
        """Create a parquet file for daily aggregated data."""
        if self._provider_type in {Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL}:
            if data_frame.first_valid_index() is not None:
                parquet_base_filename = f"{data_frame['invoice_month'].values[0]}_{parquet_base_filename}"
        file_name_suffix = PARQUET_EXT
        file_path = f"{self.local_path}/{parquet_base_filename}{file_name_suffix}"
        self._write_parquet_to_file(
            file_path, parquet_base_filename, file_name_suffix, data_frame, file_type=self.report_type
        )
        self.create_parquet_table(file_path, daily=True, partition_map=self.partition_map)

    def get_matched_tags(self, ocp_provider_uuids):
        """Get tags that match between OCP and the cloud source."""
        # Get matching tags
        cache_key = build_matching_tags_key(self.schema_name, self.provider_type)
        matched_tags = get_value_from_cache(cache_key)
        ctx = {
            "schema": self.schema_name,
            "provider_uuid": self.provider_uuid,
            "provider_type": self.provider_type,
        }
        invoice_month = self.invoice_month_date if self.invoice_month_date else self.start_date
        # If the key is in the cache but the value is None, there are no matching tags
        if matched_tags or is_key_in_cache(cache_key):
            LOG.info(log_json(msg="retreived matching tags from cache", context=ctx))
            return matched_tags
        if self.has_enabled_ocp_labels:
            enabled_tags = self.db_accessor.check_for_matching_enabled_keys()
            if enabled_tags:
                LOG.info(log_json(msg="getting matching tags from Postgres", context=ctx))
                matched_tags = self.db_accessor.get_openshift_on_cloud_matched_tags(self.bill_id)
            if not matched_tags and enabled_tags:
                LOG.info(log_json(msg="matched tags not available via Postgres", context=ctx))
                # This flag is specifically for disabling trino tag matching for specific customers.
                if is_tag_processing_disabled(self.schema_name):
                    LOG.info(log_json(msg="trino tag matching disabled for customer", context=ctx))
                    return []
                LOG.info(log_json(msg="getting matching tags from Trino", context=ctx))
                matched_tags = self.db_accessor.get_openshift_on_cloud_matched_tags_trino(
                    self.provider_uuid,
                    ocp_provider_uuids,
                    self.start_date,
                    self.end_date,
                    invoice_month_date=invoice_month,
                )
        set_value_in_cache(cache_key, matched_tags)
        return matched_tags

    def get_matched_tags_single_cluster(self, ocp_provider_uuid):
        """Get tags that match between cloud source and cluster."""
        ctx = {
            "schema": self.schema_name,
            "cloud_provider_uuid": self.provider_uuid,
            "provider_type": self.provider_type,
            "ocp_provider_uuid": ocp_provider_uuid,
        }
        matched_tags = None
        if self.has_enabled_ocp_labels:
            enabled_tags = self.db_accessor.check_for_matching_enabled_keys()
            if enabled_tags:
                LOG.info(log_json(msg="getting matching tags from Postgres", context=ctx))
                matched_tags = self.db_accessor.get_openshift_on_cloud_matched_tags(self.bill_id)
            if not matched_tags and enabled_tags:
                LOG.info(log_json(msg="matched tags not available via Postgres", context=ctx))
                # This flag is for disabling trino tag matching for specific customers.
                if is_tag_processing_disabled(self.schema_name):
                    LOG.info(log_json(msg="trino tag matching disabled for customer", context=ctx))
                    return []
                LOG.info(log_json(msg="getting matching tags from Trino", context=ctx))
                matched_tags = self.db_accessor.get_openshift_on_cloud_matched_tags_trino(
                    self.provider_uuid,
                    [ocp_provider_uuid],
                    self.start_date,
                    self.end_date,
                    invoice_month_date=self.invoice_month_date if self.invoice_month_date else self.start_date,
                )
        return matched_tags

    def create_partitioned_ocp_on_cloud_parquet(self, data_frame, parquet_base_filename):
        """Create a parquet file for daily aggregated data for each partition."""
        date_fields = {
            Provider.PROVIDER_AWS: "lineitem_usagestartdate",
            Provider.PROVIDER_AZURE: "date",
            Provider.PROVIDER_GCP: "usage_start_time",
        }
        date_field = date_fields[self.provider_type]

        unique_usage_days = data_frame[date_field].unique()
        for usage_day in unique_usage_days:
            usage_date = pd.to_datetime(usage_day).date()
            # Parquet base filename dates here DO NOT match the data written to them
            split_base_name = parquet_base_filename.split("_")
            base_file_date = split_base_name[0]
            if self.provider_type in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
                # GCP filenames start with an invoice month before the date
                base_file_date = f"{base_file_date}_{split_base_name[1]}"
            non_date_base_name = parquet_base_filename.removeprefix(base_file_date)
            usage_day_file_name = f"{usage_date}{non_date_base_name}"
            self.start_date = usage_date
            df = data_frame[data_frame[date_field] == usage_day]
            self.create_ocp_on_cloud_parquet(df, usage_day_file_name)

    def get_ocp_provider_uuids_tuple(self):
        """Get a list of provider UUIDs to process against."""
        ocp_provider_uuids = []
        ctx = {
            "schema": self.schema_name,
            "provider_uuid": self.provider_uuid,
            "provider_type": self.provider_type,
        }
        for ocp_provider_uuid, infra_tuple in self.ocp_infrastructure_map.items():
            infra_provider_uuid = infra_tuple[0]
            if infra_provider_uuid != self.provider_uuid:
                continue
            ctx |= {
                "ocp_provider_uuid": ocp_provider_uuid,
                "start_date": self.start_date,
                "report_file": self.report_file,
            }
            with OCPReportDBAccessor(self.schema_name) as accessor:
                if not accessor.get_cluster_for_provider(ocp_provider_uuid):
                    LOG.info(
                        log_json(
                            msg=f"no cluster information available - skipping OCP on {self.provider_type} processing",
                            context=ctx,
                        )
                    )
                    continue
                ocp_provider_uuids.append(ocp_provider_uuid)
        return tuple(ocp_provider_uuids)

    def process(self, parquet_base_filename, daily_data_frames):
        """Filter data and convert to parquet."""
        LOG.info(log_json(msg=f"starting OCP on {self.provider_type} to parquet processing", context=self._context))
        if not (ocp_provider_uuids := self.get_ocp_provider_uuids_tuple()):
            return
        if daily_data_frames == []:
            LOG.info(
                log_json(
                    msg=f"no OCP on {self.provider_type} daily frames to processes, skipping", context=self._context
                )
            )
            return

        if self.report_status:
            # internal masu endpoints may result in this being None, so guard this in case there is no status to update
            self.report_status.update_status(CombinedChoices.OCP_CLOUD_PROCESSING)

        # # Get OpenShift topology data
        with OCPReportDBAccessor(self.schema_name) as accessor:
            if self.provider_type == Provider.PROVIDER_GCP:
                LOG.debug("getting OpenShift topology data for GCP")
                cluster_topology = accessor.get_filtered_openshift_topology_for_multiple_providers(
                    ocp_provider_uuids, self.start_date, self.end_date
                )
            else:
                LOG.debug("getting OpenShift topology data")
                cluster_topology = accessor.get_openshift_topology_for_multiple_providers(ocp_provider_uuids)
            # Get matching tags
            matched_tags = self.get_matched_tags(ocp_provider_uuids)
            daily_data_frames = pd.concat(daily_data_frames, ignore_index=True)
            openshift_filtered_data_frame = self.ocp_on_cloud_data_processor(
                daily_data_frames, cluster_topology, matched_tags
            )

            if self.provider_type in (
                Provider.PROVIDER_GCP,
                Provider.PROVIDER_GCP_LOCAL,
                Provider.PROVIDER_AWS,
                Provider.PROVIDER_AWS_LOCAL,
                Provider.PROVIDER_AZURE,
                Provider.PROVIDER_AZURE_LOCAL,
            ):
                self.create_partitioned_ocp_on_cloud_parquet(openshift_filtered_data_frame, parquet_base_filename)
            else:
                self.create_ocp_on_cloud_parquet(openshift_filtered_data_frame, parquet_base_filename)

    def find_openshift_keys_expected_values(self, start_date, end_date, ocp_provider_uuid, matched_tag_strs):
        """
        We need to find the expected values for the openshift specific keys.
        Keys: openshift-project, openshift-node, openshift-cluster
        Ex: ("openshift-project": "project_a")
        """
        year = start_date.strftime("%Y")
        month = start_date.strftime("%m")
        matched_tags_sql = pkgutil.get_data("masu.database", "trino_sql/ocp_special_matched_tags.sql")
        matched_tags_sql = matched_tags_sql.decode("utf-8")
        matached_tags_params = {
            "schema": self.schema_name,
            "start_date": start_date,
            "year": year,
            "month": month,
            "end_date": end_date,
            "ocp_provider_uuid": ocp_provider_uuid,
            "matched_tag_array": matched_tag_strs,
        }
        LOG.info(log_json(msg="Finding expected values for openshift special tags", **matached_tags_params))
        matched_tags_result = self.db_accessor._execute_trino_multipart_sql_query(
            matched_tags_sql, bind_params=matached_tags_params
        )
        matched_tags_result = matched_tags_result[0][0]
        return matched_tags_result

    def process_ocp_cloud_trino(self, ocp_provider_uuid, start_date, end_date):
        """Populate managed_cloud_openshift_daily trino table via SQL."""
        LOG.info(
            log_json(msg=f"starting OCP on {self.provider_type} managed tables processing", context=self._context)
        )
        matched_tags = self.get_matched_tags_single_cluster(ocp_provider_uuid)
        matched_tag_strs = []
        if matched_tags:
            matched_tag_strs = [json.dumps(match).replace("{", "").replace("}", "") for match in matched_tags]
        sql_metadata = SummarySqlMetadata(
            self.db_accessor.schema, ocp_provider_uuid, self.provider_uuid, start_date, end_date, matched_tag_strs
        )
        self.db_accessor.populate_ocp_on_cloud_daily_trino(sql_metadata)
