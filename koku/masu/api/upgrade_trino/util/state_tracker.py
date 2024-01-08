import logging
import os

from api.common import log_json
from api.provider.provider_manager import ProviderManager
from api.provider.provider_manager import ProviderManagerError


LOG = logging.getLogger(__name__)


class StateTracker:
    """Tracks the state of each s3 file for the provider per bill date"""

    CONTEXT_KEY = "conversion_metadata"
    CONVERTER_VERSION = "0"
    FOUND_S3_FILE = "found_s3_file"
    DOWNLOADED_LOCALLY = "downloaded_locally"
    NO_CHANGES_NEEDED = "no_changes_needed"
    COERCE_REQUIRED = "coerce_required"
    SENT_TO_S3_COMPLETE = "sent_to_s3_complete"
    SENT_TO_S3_FAILED = "sent_to_s3_failed"
    FAILED_DTYPE_CONVERSION = "failed_data_type_conversion"

    def __init__(self, provider_uuid):
        self.files = []
        self.tracker = {}
        self.local_files = {}
        self.provider_uuid = provider_uuid

    def add_to_queue(self, bill_date_data):
        """
        Checks the provider object's metadata to see if we should start the task.

        Args:
            conversion_metadata (dict): Metadata for the conversion.

        Returns:
            bool: True if the task should be added to the queue, False otherwise.
        """
        # TODO: turn the keys here into a variable.
        if bill_date_data.get("version") != self.CONVERTER_VERSION:
            # always kick off a task if the version does not match or exist.
            return True
        if bill_date_data.get("conversion_successful"):
            # if the conversion was successful for this version do not kick
            # off a task.
            return False
        return True

    def set_state(self, s3_obj_key, state, bill_date):
        # TODO: make bill date a string.
        bill_date_files = self.tracker.get(bill_date)
        if bill_date_files:
            bill_date_files[s3_obj_key] = state
            self.tracker[bill_date] = bill_date_files
        else:
            self.tracker[bill_date] = {s3_obj_key: state}

    def add_local_file(self, s3_obj_key, local_path, bill_date):
        # TODO: make bill date a string.
        self.local_files[s3_obj_key] = local_path
        self.set_state(s3_obj_key, self.DOWNLOADED_LOCALLY, bill_date)

    def get_files_that_need_updated(self):
        """Returns a mapping of files in the s3 needs
        updating state.

         {s3_object_key: local_file_path} for
        """
        mapping = {}
        for bill_date, bill_metadata in self.tracker.items():
            bill_date_data = {}
            for s3_obj_key, state in bill_metadata.items():
                if state == self.COERCE_REQUIRED:
                    bill_date_data[s3_obj_key] = self.local_files.get(s3_obj_key)
            mapping[bill_date] = bill_date_data
        return mapping

    def generate_simulate_messages(self):
        """
        Generates the simulate messages.
        """
        for bill_date, bill_data in self.tracker.items():
            files_count = 0
            files_failed = []
            files_need_updated = []
            files_correct = []
            for s3_obj_key, state in bill_data.items():
                files_count += 1
                if state == self.COERCE_REQUIRED:
                    files_need_updated.append(s3_obj_key)
                elif state == self.NO_CHANGES_NEEDED:
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
                        bill_date=bill_date,
                    )
                )
        self._clean_local_files()

    def _clean_local_files(self):
        for file_path in self.local_files.values():
            if os.path.exists(file_path):
                os.remove(file_path)

    def _create_bill_date_metadata(self):
        # Check for incomplete files
        metadata = {}
        for bill_date, bill_metadata in self.tracker.items():
            bill_date_data = {"version": self.CONVERTER_VERSION}
            incomplete_files = []
            for file_prefix, state in bill_metadata.items():
                if state not in [self.SENT_TO_S3_COMPLETE, self.NO_CHANGES_NEEDED]:
                    file_metadata = {"key": file_prefix, "state": state}
                    incomplete_files.append(file_metadata)
            if incomplete_files:
                bill_date_data["conversion_successful"] = False
                bill_date_data["dtype_failed_files"] = incomplete_files
            if not incomplete_files:
                bill_date_data["conversion_successful"] = True
            metadata[bill_date] = bill_date_data
        return metadata

    def _check_if_complete(self):
        try:
            manager = ProviderManager(self.provider_uuid)
            context = manager.get_additional_context()
            context[self.CONTEXT_KEY] = self._create_bill_date_metadata()
            manager.model.set_additional_context(context)
            LOG.info(self.provider_uuid, log_json(msg="setting dtype states", context=context))
        except ProviderManagerError:
            pass

    def finalize_and_clean_up(self):
        self._check_if_complete()
        self._clean_local_files()
        # We can decide if we want to record
        # failed parquet conversion
