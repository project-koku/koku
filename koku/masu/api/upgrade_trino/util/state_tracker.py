import logging
import os

from api.common import log_json
from api.provider.provider_manager import ProviderManager
from api.provider.provider_manager import ProviderManagerError


LOG = logging.getLogger(__name__)


class StateTracker:
    FOUND_S3_FILE = "found_s3_file"
    DOWNLOADED_LOCALLY = "downloaded_locally"
    NO_CHANGES_NEEDED = "no_changes_needed"
    COERCE_REQUIRED = "coerce_required"
    SENT_TO_S3_COMPLETE = "sent_to_s3_complete"
    S3_FILE_DELETED = "s3_file_deleted"
    SENT_TO_S3_FAILED = "sent_to_s3_failed"
    FAILED_DTYPE_CONVERSION = "failed_data_type_conversion"

    def __init__(self, provider_uuid):
        self.files = []
        self.tracker = {}
        self.local_files = {}
        self.provider_uuid = provider_uuid
        self.context_key = "dtype_conversion"
        self.failed_files_key = "dtype_failed_files"

    def set_state(self, s3_obj_key, state):
        self.tracker[s3_obj_key] = state

    def add_local_file(self, s3_obj_key, local_path):
        self.local_files[s3_obj_key] = local_path
        self.tracker[s3_obj_key] = self.DOWNLOADED_LOCALLY

    def get_files_that_need_updated(self):
        """Returns a mapping of files in the s3 needs
        updating state.

         {s3_object_key: local_file_path} for
        """
        mapping = {}
        for s3_obj_key, state in self.tracker.items():
            if state == self.COERCE_REQUIRED:
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
            LOG.info(log_json(self.provider_uuid, msg=substring, file_count=len(files_list), total_count=files_count))

    def _clean_local_files(self):
        for file_path in self.local_files.values():
            os.remove(file_path)

    def _check_for_incomplete_files(self):
        incomplete_files = []
        for file_prefix, state in self.tracker.items():
            if state not in [self.SENT_TO_S3_COMPLETE, self.NO_CHANGES_NEEDED]:
                file_metadata = {"key": file_prefix, "state": state}
                incomplete_files.append(file_metadata)
        return incomplete_files

    def _check_if_complete(self):
        incomplete_files = self._check_for_incomplete_files()
        try:
            manager = ProviderManager(self.provider_uuid)
            context = manager.get_additional_context()
            context[self.context_key] = True
            if incomplete_files:
                context[self.context_key] = False
                context[self.failed_files_key] = incomplete_files
            manager.model.set_additional_context(context)
            LOG.info(self.provider_uuid, log_json(msg="setting dtype states", context=context))
        except ProviderManagerError:
            pass

    def finalize_and_clean_up(self):
        self._check_if_complete()
        self._clean_local_files()
        # We can decide if we want to record
        # failed parquet conversion
