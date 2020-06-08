#
# Copyright 2018 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Report manifest database accessor for cost usage reports."""
from celery.utils.log import get_task_logger
from django.db import transaction
from django.db.models import F
from django.db.models.expressions import Window
from django.db.models.functions import RowNumber
from tenant_schemas.utils import schema_context

from masu.database.koku_database_access import KokuDBAccess
from masu.external.date_accessor import DateAccessor
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus

LOG = get_task_logger(__name__)


class ReportManifestDBAccessor(KokuDBAccess):
    """Class to interact with the koku database for CUR processing statistics."""

    def __init__(self):
        """Access the AWS report manifest database table."""
        self._schema = "public"
        super().__init__(self._schema)
        self._table = CostUsageReportManifest
        self.date_accessor = DateAccessor()

    @classmethod
    def increment_file_process_count(cls, manifest_id):
        """Increment manifest processed report count."""
        with transaction.atomic():
            with schema_context("public"):
                manifest = CostUsageReportManifest.objects.select_for_update().get(id=manifest_id)
                manifest.num_processed_files += 1
                manifest.save()

    def get_manifest(self, assembly_id, provider_uuid):
        """Get the manifest associated with the provided provider and id."""
        query = self._get_db_obj_query()
        return query.filter(provider_id=provider_uuid).filter(assembly_id=assembly_id).first()

    def get_manifest_by_id(self, manifest_id):
        """Get the manifest by id."""
        with schema_context(self._schema):
            query = self._get_db_obj_query()
            return query.filter(id=manifest_id).first()

    def mark_manifest_as_updated(self, manifest):
        """Update the updated timestamp."""
        if manifest:
            manifest.manifest_updated_datetime = self.date_accessor.today_with_timezone("UTC")
            manifest.save()

    def mark_manifest_as_completed(self, manifest):
        """Update the updated timestamp."""
        if manifest:
            manifest.manifest_completed_datetime = self.date_accessor.today_with_timezone("UTC")
            manifest.save()

    def add(self, **kwargs):
        """
        Add a new row to the CUR stats database.

        Args:
            kwargs (dict): Fields containing CUR Manifest attributes.
                Valid keys are: assembly_id,
                                billing_period_start_datetime,
                                num_processed_files (optional),
                                num_total_files,
                                provider_uuid,
        Returns:
            None

        """
        if "manifest_creation_datetime" not in kwargs:
            kwargs["manifest_creation_datetime"] = self.date_accessor.today_with_timezone("UTC")

        if "num_processed_files" not in kwargs:
            kwargs["num_processed_files"] = 0

        # The Django model insists on calling this field provider_id
        if "provider_uuid" in kwargs:
            uuid = kwargs.pop("provider_uuid")
            kwargs["provider_id"] = uuid

        return super().add(**kwargs)

    def manifest_ready_for_summary(self, manifest_id):
        """Determine if the manifest is ready to summarize."""
        return not self.is_last_completed_datetime_null(manifest_id)

    def is_last_completed_datetime_null(self, manifest_id):
        """Determine if nulls exist in last_completed_datetime for manifest_id.

        If the record does not exist, that is equivalent to a null completed dateimte.
        Return True if record either doesn't exist or if null `last_completed_datetime`.
        Return False otherwise.

        """
        record = CostUsageReportStatus.objects.filter(manifest_id=manifest_id)
        if record:
            return record.filter(last_completed_datetime__isnull=True).exists()
        return True

    def get_manifest_list_for_provider_and_bill_date(self, provider_uuid, bill_date):
        """Return all manifests for a provider and bill date."""
        filters = {"provider_id": provider_uuid, "billing_period_start_datetime__date": bill_date}
        return CostUsageReportManifest.objects.filter(**filters).all()

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
                    order_by=F("manifest_creation_datetime").desc(),
                )
            )
            .order_by("row_number")
        )
        for manifest in [manifest for manifest in manifests if manifest.row_number == 1]:
            # loop through the manifests and decide if they have finished processing
            processed = manifest.num_total_files == manifest.num_processed_files
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
        delete_count = CostUsageReportManifest.objects.filter(
            provider__type=provider_type, billing_period_start_datetime__lt=expired_date
        ).delete()[0]
        LOG.info(
            "Removed %s CostUsageReportManifest(s) for provider type %s that had a billing period start date before %s",
            delete_count,
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
        delete_count = CostUsageReportManifest.objects.filter(
            provider_id=provider_uuid, billing_period_start_datetime__lt=expired_date
        ).delete()
        LOG.info(
            "Removed %s CostUsageReportManifest(s) for provider_uuid %s that had a billing period start date before %s",
            delete_count,
            provider_uuid,
            expired_date,
        )
