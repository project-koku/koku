#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Report manifest database accessor for cost usage reports."""
import logging
from datetime import date
from datetime import datetime

from django.db import transaction
from django.db.models import DateField
from django.db.models import DateTimeField
from django.db.models import F
from django.db.models import Func
from django.db.models import Max
from django.db.models import Value
from django.db.models.expressions import Window
from django.db.models.functions import Cast
from django.db.models.functions import RowNumber
from django.utils import timezone

from api.common import log_json
from koku.database import cascade_delete
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus
from reporting_common.states import ManifestState

LOG = logging.getLogger(__name__)


class ReportManifestDBAccessor:
    """Class to interact with the koku database for CUR processing statistics."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_manifest(self, assembly_id, provider_uuid):
        """Get the manifest associated with the provided provider and id."""
        return CostUsageReportManifest.objects.filter(provider_id=provider_uuid, assembly_id=assembly_id).first()

    def get_manifest_by_id(self, manifest_id):
        """Get the manifest by id."""
        return CostUsageReportManifest.objects.filter(id=manifest_id).first()

    def mark_manifests_as_completed(self, manifest_list):
        """Update the completed timestamp."""
        completed_datetime = timezone.now()
        if manifest_list:
            bulk_manifest_query = CostUsageReportManifest.objects.filter(id__in=manifest_list)
            for manifest in bulk_manifest_query:
                ctx = {
                    "manifest_id": manifest.id,
                    "assembly_id": manifest.assembly_id,
                    "provider_uuid": manifest.provider_id,
                    "completed_datetime": completed_datetime,
                }
                LOG.info(log_json(msg="marking manifest complete", context=ctx))
                manifest.completed_datetime = completed_datetime
                manifest.save()
                LOG.info(log_json(msg="manifest marked complete", context=ctx))

    def update_number_of_files_for_manifest(self, manifest):
        """Update the number of files for manifest."""
        set_num_of_files = CostUsageReportStatus.objects.filter(manifest_id=manifest.id).count()
        if manifest:
            manifest.num_total_files = set_num_of_files
            manifest.save(update_fields=["num_total_files"])

    def update_manifest_state(self, step, interval, manifest_id=None):
        """Update the number of files for manifest."""
        if manifest_id:
            with transaction.atomic():  # prevent collisions
                manifest = CostUsageReportManifest.objects.select_for_update().get(id=manifest_id)
                if manifest:
                    time_now = timezone.now()
                    if not manifest.state:
                        manifest.state = {}
                    if interval == ManifestState.START:
                        # We need to clear END times to prevent false positives when reprocessing
                        manifest.state[step] = {}
                    manifest.state[step][interval] = time_now.isoformat()
                    if interval == ManifestState.END or interval == ManifestState.FAILED:
                        manifest.state[step]["time_taken_seconds"] = (
                            time_now - datetime.fromisoformat(manifest.state[step][ManifestState.START])
                        ).seconds
                    manifest.save(update_fields=["state"])

    def manifest_ready_for_summary(self, manifest_id):
        """Determine if the manifest is ready to summarize."""
        return not self.is_completed_datetime_null(manifest_id)

    def number_of_files(self, manifest_id):
        """Return the number of files in a manifest."""
        return CostUsageReportStatus.objects.filter(manifest_id=manifest_id).count()

    def number_of_files_processed(self, manifest_id):
        """Return the number of files processed in a manifest."""
        return CostUsageReportStatus.objects.filter(manifest_id=manifest_id, completed_datetime__isnull=False).count()

    def is_completed_datetime_null(self, manifest_id):
        """Determine if nulls exist in completed_datetime for manifest_id.

        If the record does not exist, that is equivalent to a null completed datetime.
        Return True if record either doesn't exist or if null `completed_datetime`.
        Return False otherwise.

        """
        if record := CostUsageReportStatus.objects.filter(manifest_id=manifest_id):
            return record.filter(completed_datetime__isnull=True).exists()
        return True

    def get_manifest_list_for_provider_and_bill_date(self, provider_uuid, bill_date):
        """Return all manifests for a provider and bill date."""
        filters = {"provider_id": provider_uuid, "billing_period_start_datetime__date": bill_date}
        return CostUsageReportManifest.objects.filter(**filters).all()

    def get_last_manifest_upload_datetime(self, provider_uuid=None):
        """Return all ocp manifests with lastest upload datetime."""
        filters = {}
        if provider_uuid:
            filters["provider_id"] = provider_uuid
        return (
            CostUsageReportManifest.objects.filter(**filters)
            .values("provider_id")
            .annotate(most_recent_manifest=Max("creation_datetime"))
        )

    def get_last_seen_manifest_ids(self, bill_date):
        """Return a tuple containing the assembly_id of the last seen manifest and a boolean

        The boolean will state whether or not that manifest has been processed."""
        assembly_ids = []
        # The following query uses a window function to rank the manifests for all the providers,
        # and then just pulls out the top ranked (most recent) manifests
        manifests = (
            CostUsageReportManifest.objects.filter(billing_period_start_datetime=bill_date)
            .annotate(
                row_number=Window(
                    expression=RowNumber(),
                    partition_by=F("provider_id"),
                    order_by=F("creation_datetime").desc(),
                )
            )
            .order_by("row_number")
        )
        for manifest in [manifest for manifest in manifests if manifest.row_number == 1]:
            # loop through the manifests and decide if they have finished processing
            processed = self.manifest_ready_for_summary(manifest.id)
            # if all of the files for the manifest have been processed we don't want to add it
            # to assembly_ids because it is safe to delete
            if not processed:
                assembly_ids.append(manifest.assembly_id)
        return assembly_ids

    def purge_expired_report_manifest(self, provider_type, expired_date):
        """
        Deletes Cost usage Report Manifests older than expired_date.

        Args:
            provider_type   (String) the provider type to delete associated manifests
            expired_date (datetime.datetime) delete all manifests older than this date, exclusive.
        """
        manifests_to_delete = CostUsageReportManifest.objects.filter(
            provider__type=provider_type, billing_period_start_datetime__lt=expired_date
        )
        count = manifests_to_delete.count()
        cascade_delete(manifests_to_delete.query.model, manifests_to_delete)
        LOG.info(
            "Removed %s CostUsageReportManifest(s) for provider type %s that had a billing period start date before %s",
            count,
            provider_type,
            expired_date,
        )

    def purge_expired_report_manifest_provider_uuid(self, provider_uuid, expired_date):
        """
        Delete cost usage reports older than expired_date and provider_uuid.

        Args:
            provider_uuid (uuid) The provider uuid to use to delete associated manifests
            expired_date (datetime.datetime) delete all manifests older than this date, exclusive.
        """
        manifests_to_delete = CostUsageReportManifest.objects.filter(
            provider_id=provider_uuid, billing_period_start_datetime__lt=expired_date
        )
        count = manifests_to_delete.count()
        cascade_delete(manifests_to_delete.query.model, manifests_to_delete)
        LOG.info(
            "Removed %s CostUsageReportManifest(s) for provider_uuid %s that had a billing period start date before %s",
            count,
            provider_uuid,
            expired_date,
        )

    def get_s3_csv_cleared(self, manifest: CostUsageReportManifest) -> bool:
        """Return whether we have cleared CSV files from S3 for this manifest."""
        return manifest.s3_csv_cleared if manifest else False

    def mark_s3_csv_cleared(self, manifest: CostUsageReportManifest) -> None:
        """Mark CSV files have been cleared from S3 for this manifest."""
        if manifest:
            manifest.s3_csv_cleared = True
            manifest.save(update_fields=["s3_csv_cleared"])

    def should_s3_parquet_be_cleared(self, manifest: CostUsageReportManifest) -> bool:
        """
        Determine if the s3 parquet files should be removed.

        This is only used for OCP manifests which we can track via the cluster-id.
        If there is a cluster-id, we check if this manifest is for daily files. If so,
        we should clear the parquet files, otherwise we dont.
        """
        if not manifest:
            return False
        if not manifest.cluster_id:
            return True
        result = manifest.operator_daily_reports
        LOG.info(
            log_json(
                msg=f"s3 bucket should be cleared: {result}",
                manifest_uuid=manifest.assembly_id,
            )
        )
        return result

    def get_s3_parquet_cleared(self, manifest: CostUsageReportManifest, report_key: str = None) -> bool:
        """Return whether we have cleared CSV files from S3 for this manifest."""
        if not manifest:
            return False
        if manifest.cluster_id and report_key:
            return manifest.s3_parquet_cleared_tracker.get(report_key)
        return manifest.s3_parquet_cleared

    def mark_s3_parquet_cleared(self, manifest: CostUsageReportManifest, report_key: str = None) -> None:
        """Mark Parquet files have been cleared from S3 for this manifest."""
        if not manifest:
            return
        if manifest.cluster_id and report_key:
            manifest.s3_parquet_cleared_tracker[report_key] = True
            update_fields = ["s3_parquet_cleared_tracker"]
        else:
            manifest.s3_parquet_cleared = True
            update_fields = ["s3_parquet_cleared"]
        manifest.save(update_fields=update_fields)

    def set_manifest_daily_start_date(self, manifest_id: int, date_input: date) -> date | None:
        """
        Mark manifest processing daily archive start date.
        Used to prevent grabbing different starts from partial processed data
        """
        # Be race condition aware
        with transaction.atomic():
            # Check one last time another worker has not set this already
            check_processing_date = ReportManifestDBAccessor().get_manifest_daily_start_date(manifest_id)
            if check_processing_date:
                return check_processing_date
            manifest = CostUsageReportManifest.objects.select_for_update().get(id=manifest_id)
            if manifest:
                manifest.daily_archive_start_date = date_input
                manifest.save(update_fields=["daily_archive_start_date"])
                return date_input

    def get_manifest_daily_start_date(self, manifest_id: int) -> date | None:
        """
        Get manifest processing daily archive start date.
        Used to prevent grabbing different starts from partial processed data
        """
        manifest = self.get_manifest_by_id(manifest_id)
        if manifest:
            if manifest.daily_archive_start_date:
                return manifest.daily_archive_start_date.date()

    def update_and_get_day_file(self, day, manifest_id):
        with transaction.atomic():
            # With split payloads, we could have a race condition trying to update the `report_tracker`.
            # using a transaction and `select_for_update` should minimize the risk of multiple
            # workers trying to update this field at the same time by locking the manifest during update.
            manifest = CostUsageReportManifest.objects.select_for_update().get(id=manifest_id)
            if not manifest.report_tracker.get(day):
                manifest.report_tracker[day] = 0
            counter = manifest.report_tracker[day]
            manifest.report_tracker[day] = counter + 1
            manifest.save(update_fields=["report_tracker"])
            return f"{day}_manifestid-{manifest_id}_{counter}.csv"

    def get_manifest_list_for_provider_and_date_range(self, provider_uuid, start_date, end_date):
        """Return a list of GCP manifests for a date range."""
        manifests = (
            CostUsageReportManifest.objects.filter(provider_id=provider_uuid)
            .annotate(
                partition_date=Cast(
                    Func(F("assembly_id"), Value("|"), Value(1), function="split_part", output_field=DateField()),
                    output_field=DateField(),
                ),
                previous_export_time=Cast(
                    Func(F("assembly_id"), Value("|"), Value(2), function="split_part", output_field=DateTimeField()),
                    output_field=DateTimeField(),
                ),
            )
            .filter(partition_date__gte=start_date, partition_date__lte=end_date)
        )
        return manifests

    def bulk_delete_manifests(self, provider_uuid, manifest_id_list):
        """
        Deletes a specific manifest given manifest_id & provider_uuid
        Args:
            provider_uuid (uuid): The provider uuid to use to delete associated manifests
            manifest_id_list (list): list of manifest ids to delete.
        """
        if not manifest_id_list:
            return
        msg = f"""
        Attempting to delete the following manifests:
           manifest_list: {manifest_id_list}
           manifest_count: {len(manifest_id_list)}
        """
        LOG.info(msg)
        manifests_to_delete = CostUsageReportManifest.objects.filter(
            provider_id=provider_uuid, id__in=manifest_id_list
        )
        count = manifests_to_delete.count()
        cascade_delete(manifests_to_delete.query.model, manifests_to_delete)
        LOG.info(
            "Removed %s manifests for provider_uuid %s",
            count,
            provider_uuid,
        )
