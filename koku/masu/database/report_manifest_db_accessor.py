#
# Copyright 2020 Red Hat, Inc.
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

    # pylint: disable=arguments-differ
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

    # pylint: disable=no-self-use
    def get_last_report_completed_datetime(self, manifest_id):
        """Get the most recent report processing completion time for a manifest."""
        result = (
            CostUsageReportStatus.objects.filter(manifest_id=manifest_id).order_by("-last_completed_datetime").first()
        )
        return result.last_completed_datetime

    def reset_manifest(self, manifest_id):
        """Return the manifest to a state as if it had not been processed.

        This sets the number of processed files to zero and
        nullifies the started and completed times on the reports.
        """
        manifest = self.get_manifest_by_id(manifest_id)
        manifest.num_processed_files = 0
        manifest.save()

        files = CostUsageReportStatus.objects.filter(id=manifest_id).all()
        for file in files:
            file.last_completed_datetime = None
            file.last_started_datetime = None
            file.save()

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

    def delete_cost_usage_reports_older_than(self, provider_type, billing_period_start_datetime):
        """
        Deletes Cost usage Reports older than expiration_date

        Args:
            provider_type   (String) the provider type to delete
            billing_period_start_datetime (datetime.datetime) delete all manifests older than this date, exclusive.
        """
        delete_count = CostUsageReportManifest.objects.filter(
            provider__type=provider_type, billing_period_start_datetime__lt=billing_period_start_datetime
        ).delete()
        LOG.info(
            "Removed %s CostUsageReportManifest(s) before billing period start %s",
            delete_count,
            billing_period_start_datetime,
        )
