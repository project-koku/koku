import logging
import os
from datetime import date

from api.common import log_json
from api.provider.provider_manager import ProviderManager
from api.provider.provider_manager import ProviderManagerError
from masu.api.upgrade_trino.util.constants import ConversionContextKeys
from masu.api.upgrade_trino.util.constants import ConversionStates as cstates
from masu.api.upgrade_trino.util.constants import CONVERTER_VERSION


LOG = logging.getLogger(__name__)


class StateTracker:
    """Tracks the state of each s3 file for the provider per bill date"""

    def __init__(self, provider_uuid: str, bill_date: date):
        self.files = []
        self.tracker = {}
        self.local_files = {}
        self.provider_uuid = provider_uuid
        self.bill_date_str = bill_date.strftime("%Y-%m-%d")

    def add_to_queue(self, conversion_metadata):
        """
        Checks the provider object's metadata to see if we should start the task.

        Args:
            conversion_metadata (dict): Metadata for the conversion.

        Returns:
            bool: True if the task should be added to the queue, False otherwise.
        """
        bill_metadata = conversion_metadata.get(self.bill_date_str, {})
        if bill_metadata.get(ConversionContextKeys.version) != CONVERTER_VERSION:
            # always kick off a task if the version does not match or exist.
            return True
        if bill_metadata.get(ConversionContextKeys.successful):
            # if the conversion was successful for this version do not kick
            # off a task.
            LOG.info(
                log_json(
                    self.provider_uuid,
                    msg="Conversion already marked as successful",
                    bill_date=self.bill_date_str,
                    provider_uuid=self.provider_uuid,
                )
            )
            return False
        return True

    def set_state(self, s3_obj_key, state):
        self.tracker[s3_obj_key] = state

    def add_local_file(self, s3_obj_key, local_path):
        self.local_files[s3_obj_key] = local_path
        self.tracker[s3_obj_key] = cstates.downloaded_locally

    def get_files_that_need_updated(self):
        """Returns a mapping of files in the s3 needs
        updating state.

         {s3_object_key: local_file_path} for
        """
        mapping = {}
        for s3_obj_key, state in self.tracker.items():
            if state == cstates.coerce_required:
                mapping[s3_obj_key] = self.local_files.get(s3_obj_key)
        return mapping

    def generate_simulate_messages(self):
        """
        Generates the simulate messages.
        """

        files_count = 0
        files_failed = []
        files_need_updated = []
        files_correct = []
        for s3_obj_key, state in self.tracker.items():
            files_count += 1
            if state == cstates.coerce_required:
                files_need_updated.append(s3_obj_key)
            elif state == cstates.no_changes_needed:
                files_correct.append(s3_obj_key)
            else:
                files_failed.append(s3_obj_key)
        simulate_info = {
            "Files that have all correct data_types.": files_correct,
            "Files that need to be updated.": files_need_updated,
            "Files that failed to convert.": files_failed,
        }
        for substring, files_list in simulate_info.items():
            LOG.info(
                log_json(
                    self.provider_uuid,
                    msg=substring,
                    file_count=len(files_list),
                    total_count=files_count,
                    bill_date=self.bill_date_str,
                )
            )
        self._clean_local_files()
        return simulate_info

    def _clean_local_files(self):
        for file_path in self.local_files.values():
            if os.path.exists(file_path):
                os.remove(file_path)

    def _create_bill_date_metadata(self):
        # Check for incomplete files
        bill_date_data = {"version": CONVERTER_VERSION}
        incomplete_files = []
        for file_prefix, state in self.tracker.items():
            if state not in [cstates.s3_complete, cstates.no_changes_needed]:
                file_metadata = {"key": file_prefix, "state": state}
                incomplete_files.append(file_metadata)
        if incomplete_files:
            bill_date_data[ConversionContextKeys.successful] = False
            bill_date_data[ConversionContextKeys.failed_files] = incomplete_files
        if not incomplete_files:
            bill_date_data[ConversionContextKeys.successful] = True
        return bill_date_data

    def _check_if_complete(self):
        try:
            manager = ProviderManager(self.provider_uuid)
            context = manager.get_additional_context()
            conversion_metadata = context.get(ConversionContextKeys.metadata, {})
            conversion_metadata[self.bill_date_str] = self._create_bill_date_metadata()
            context[ConversionContextKeys.metadata] = conversion_metadata
            manager.model.set_additional_context(context)
            LOG.info(self.provider_uuid, log_json(msg="setting dtype states", context=context))
        except ProviderManagerError:
            pass

    def finalize_and_clean_up(self):
        self._check_if_complete()
        self._clean_local_files()
