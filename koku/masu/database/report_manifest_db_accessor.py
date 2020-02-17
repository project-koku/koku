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
from tenant_schemas.utils import schema_context

from masu.database.koku_database_access import KokuDBAccess
from masu.external.date_accessor import DateAccessor
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus


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
        manifest.manifest_updated_datetime = self.date_accessor.today_with_timezone("UTC")
        manifest.save()

    def mark_manifest_as_completed(self, manifest):
        """Update the updated timestamp."""
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

    def get_last_seen_manifest_id(self, bill_date):
        """Return a tuple containing the assembly_id of the last seen manifest and a boolean

        The boolean will state whether or not that manifest has been processed."""
        # get the assembly id that was last seen
        # similar to select assembly_id from reporting_common_costusagereportmanifest where provider_id =
        # '01f0bb5f-f98a-453a-ad85-97698aac3895' and
        # billing_period_start_datetime = '2020-01-01 00:00:00+00' order by id desc limit 1;
        assembly_id = None
        processed = True
        filters = {"billing_period_start_datetime__date": bill_date}
        report = CostUsageReportManifest.objects.filter(**filters).order_by("-manifest_creation_datetime").first()
        if report:
            assembly_id = report.assembly_id
            num_total_files = report.num_total_files
            num_processed_files = report.num_processed_files
            processed = num_total_files == num_processed_files

        print("\n\n\n\n\n report: ")
        print(report)
        print(type(report))
        return assembly_id, processed
        # assembly_id = report.assembly_id
        # print(assembly_id)
        # # now check if that manifest associated with that id has been processed
        # num_total_files = report.num_total_files
        # num_processed_files = report.num_processed_files
        # processed = (num_processed_files == num_total_files)
        # print(processed)
        # print(num_processed_files)
        # print(num_total_files)
        # processed = False
        # return ('d597fe25-2c6a-4522-a0e5-d937602ec384', False)
