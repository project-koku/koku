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

from masu.database.koku_database_access import KokuDBAccess
from masu.external.date_accessor import DateAccessor
from reporting_common.models import CostUsageReportManifest


class ReportManifestDBAccessor(KokuDBAccess):
    """Class to interact with the koku database for CUR processing statistics."""

    def __init__(self):
        """Access the AWS report manifest database table."""
        self._schema = 'public'
        super().__init__(self._schema)
        self._table = CostUsageReportManifest
        self.date_accessor = DateAccessor()

    def get_manifest(self, assembly_id, provider_id):
        """Get the manifest associated with the provided provider and id."""
        query = self._get_db_obj_query()
        return query.filter(provider_id=provider_id)\
            .filter(assembly_id=assembly_id).first()

    def get_manifest_by_id(self, manifest_id):
        """Get the manifest by id."""
        query = self._get_db_obj_query()
        return query.filter(id=manifest_id).first()

    def mark_manifest_as_updated(self, manifest):
        """Update the updated timestamp."""
        manifest.manifest_updated_datetime = \
            self.date_accessor.today_with_timezone('UTC')

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
                                provider_id,
        Returns:
            None

        """
        if 'manifest_creation_datetime' not in kwargs:
            kwargs['manifest_creation_datetime'] = \
                self.date_accessor.today_with_timezone('UTC')

        if 'num_processed_files' not in kwargs:
            kwargs['num_processed_files'] = 0

        return super().add(**kwargs)
