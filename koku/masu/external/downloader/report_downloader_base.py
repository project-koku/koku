#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Report Downloader."""
import logging
from tempfile import mkdtemp

from django.db.utils import IntegrityError

from api.common import log_json
from api.provider.models import Provider
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from reporting_common.models import CostUsageReportManifest

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
        LOG.info(log_json(self.tracing_id, msg=msg))

        manifest_entry = CostUsageReportManifest.objects.filter(
            assembly_id=assembly_id, provider=self._provider_uuid
        ).first()
        if not manifest_entry:
            manifest_dict = kwargs | {
                "assembly_id": assembly_id,
                "billing_period_start_datetime": billing_start,
                "num_total_files": num_of_files,
                "provider_uuid": self._provider_uuid,
                "manifest_modified_datetime": manifest_modified_datetime,
            }
            # the provider uuid must go in `provider_id`. Explicitly set `provider_uuid` above in case
            # kwargs contains it. Then we update the key here:
            manifest_dict["provider_id"] = manifest_dict.pop("provider_uuid")
            try:
                manifest_entry, _ = CostUsageReportManifest.objects.get_or_create(**manifest_dict)
            except IntegrityError:
                manifest_entry = CostUsageReportManifest.objects.filter(
                    assembly_id=assembly_id, provider=self._provider_uuid
                ).first()

        if not manifest_entry:
            # if we somehow end up here, then wow
            msg = f"Manifest entry not found for given manifest {manifest_dict}."
            provider = Provider.objects.filter(uuid=self._provider_uuid).first()
            if not provider:
                msg = f"Provider entry not found for {self._provider_uuid}."
                LOG.warning(log_json(self.tracing_id, msg=msg, context=self.context))
                raise ReportDownloaderError(msg)
            LOG.warning(log_json(self.tracing_id, msg=msg, context=self.context))
            raise IntegrityError(msg)

        with ReportManifestDBAccessor() as manifest_accessor:
            if num_of_files != manifest_entry.num_total_files:
                manifest_accessor.update_number_of_files_for_manifest(manifest_entry)
            manifest_accessor.mark_manifest_as_updated(manifest_entry)

        return manifest_entry.id
