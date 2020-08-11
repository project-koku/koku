#
# Copyright 2018 Red Hat, Inc.
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
"""Report Downloader."""
import logging
from tempfile import mkdtemp

from django.db.utils import IntegrityError

from api.common import log_json
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor

LOG = logging.getLogger(__name__)


class ReportDownloaderBase:
    """
    Download cost reports from a provider.

    Base object class for downloading cost reports from a cloud provider.
    """

    def __init__(self, download_path=None, **kwargs):
        """
        Create a downloader.

        Args:
            download_path (String) filesystem path to store downloaded files

        Kwargs:
            customer_name     (String) customer name
            access_credential (Dict) provider access credentials
            report_source     (String) cost report source
            provider_type     (String) cloud provider type
            provider_uuid     (String) cloud provider uuid
            report_name       (String) cost report name

        """
        if download_path:
            self.download_path = download_path
        else:
            self.download_path = mkdtemp(prefix="masu")
        self._cache_key = kwargs.get("cache_key")
        self._provider_uuid = kwargs.get("provider_uuid")
        self.request_id = kwargs.get("request_id")
        self.account = kwargs.get("account")
        self.context = {"request_id": self.request_id, "provider_uuid": self._provider_uuid, "account": self.account}

    def _get_existing_manifest_db_id(self, assembly_id):
        """Return a manifest DB object if it exists."""
        manifest_id = None
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest(assembly_id, self._provider_uuid)
            if manifest:
                manifest_id = manifest.id
        return manifest_id

    def _process_manifest_db_record(self, assembly_id, billing_start, num_of_files):
        """Insert or update the manifest DB record."""
        LOG.info("Inserting/updating manifest in database for assembly_id: %s", assembly_id)

        with ReportManifestDBAccessor() as manifest_accessor:
            manifest_entry = manifest_accessor.get_manifest(assembly_id, self._provider_uuid)

            if not manifest_entry:
                msg = f"No manifest entry found in database. Adding for bill period start: {billing_start}"
                LOG.info(log_json(self.request_id, msg, self.context))
                manifest_dict = {
                    "assembly_id": assembly_id,
                    "billing_period_start_datetime": billing_start,
                    "num_total_files": num_of_files,
                    "provider_uuid": self._provider_uuid,
                }
                try:
                    manifest_entry = manifest_accessor.add(**manifest_dict)
                except IntegrityError as error:
                    msg = (
                        f"Manifest entry uniqueness collision: Error {error}. "
                        "Manifest already added, getting manifest_entry_id."
                    )
                    LOG.warning(log_json(self.request_id, msg, self.context))
                    with ReportManifestDBAccessor() as manifest_accessor:
                        manifest_entry = manifest_accessor.get_manifest(assembly_id, self._provider_uuid)
            if not manifest_entry:
                msg = f"Manifest entry not found for given manifest {manifest_dict}."
                with ProviderDBAccessor(self._provider_uuid) as provider_accessor:
                    provider = provider_accessor.get_provider()
                    if not provider:
                        msg = f"Provider entry not found for {self._provider_uuid}."
                LOG.warning(log_json(self.request_id, msg, self.context))
                raise IntegrityError(msg)
            else:
                manifest_accessor.mark_manifest_as_updated(manifest_entry)
                manifest_id = manifest_entry.id

        return manifest_id
