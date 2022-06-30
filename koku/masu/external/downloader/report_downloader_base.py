#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Report Downloader."""
import logging
from tempfile import mkdtemp

from django.db.utils import IntegrityError

from api.common import log_json
from koku.database import FKViolation
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor

LOG = logging.getLogger(__name__)


class ReportDownloaderWarning(Exception):
    """A class for warnings related to report downloading"""


class ReportDownloaderError(Exception):
    """An exception class for base class errors"""


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
            credentials       (Dict) provider access credentials
            data_source       (Dict) cost report source
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
        self._provider_type = kwargs.get("provider_type")
        self.request_id = kwargs.get("request_id")  # TODO: Remove this once the downloaders have been updated
        self.tracing_id = kwargs.get("tracing_id")
        self.account = kwargs.get("account")
        self.context = {
            "provider_uuid": self._provider_uuid,
            "provider_type": self._provider_type,
            "account": self.account,
        }

    def _get_existing_manifest_db_id(self, assembly_id):
        """Return a manifest DB object if it exists."""
        manifest_id = None
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest(assembly_id, self._provider_uuid)
            if manifest:
                manifest_id = manifest.id
        return manifest_id

    def _process_manifest_db_record(
        self, assembly_id, billing_start, num_of_files, manifest_modified_datetime, **kwargs
    ):
        """Insert or update the manifest DB record."""
        msg = f"Inserting/updating manifest in database for assembly_id: {assembly_id}"
        LOG.info(log_json(self.tracing_id, msg))

        with ReportManifestDBAccessor() as manifest_accessor:
            manifest_entry = manifest_accessor.get_manifest(assembly_id, self._provider_uuid)

            if not manifest_entry:
                msg = f"No manifest entry found in database. Adding for bill period start: {billing_start}"
                LOG.info(log_json(self.tracing_id, msg, self.context))
                manifest_dict = {
                    "assembly_id": assembly_id,
                    "billing_period_start_datetime": billing_start,
                    "num_total_files": num_of_files,
                    "provider_uuid": self._provider_uuid,
                    "manifest_modified_datetime": manifest_modified_datetime,
                }
                manifest_dict.update(kwargs)
                try:
                    manifest_entry = manifest_accessor.add(**manifest_dict)
                except IntegrityError as error:
                    fk_violation = FKViolation(error)
                    if fk_violation:
                        LOG.warning(fk_violation)
                        raise ReportDownloaderError(f"Method: _process_manifest_db_record :: {fk_violation}")
                    msg = (
                        f"Manifest entry uniqueness collision: Error {error}. "
                        "Manifest already added, getting manifest_entry_id."
                    )
                    LOG.warning(log_json(self.tracing_id, msg, self.context))
                    with ReportManifestDBAccessor() as manifest_accessor:
                        manifest_entry = manifest_accessor.get_manifest(assembly_id, self._provider_uuid)
            if not manifest_entry:
                msg = f"Manifest entry not found for given manifest {manifest_dict}."
                with ProviderDBAccessor(self._provider_uuid) as provider_accessor:
                    provider = provider_accessor.get_provider()
                    if not provider:
                        msg = f"Provider entry not found for {self._provider_uuid}."
                        LOG.warning(log_json(self.tracing_id, msg, self.context))
                        raise ReportDownloaderError(msg)
                LOG.warning(log_json(self.tracing_id, msg, self.context))
                raise IntegrityError(msg)
            else:
                if num_of_files != manifest_entry.num_total_files:
                    manifest_accessor.update_number_of_files_for_manifest(manifest_entry)
                manifest_accessor.mark_manifest_as_updated(manifest_entry)
                manifest_id = manifest_entry.id

        return manifest_id
