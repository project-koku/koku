from common.enum import StrEnum

# Update this to trigger the converter to run again
# even if marked as successful
CONVERTER_VERSION = "2"


class ConversionContextKeys(StrEnum):
    metadata = "conversion_metadata"
    version = "version"
    successful = "successful"
    failed_files = "dtype_failed_files"


class ConversionStates(StrEnum):
    found_s3_file = "found_s3_file"
    downloaded_locally = "downloaded_locally"
    no_changes_needed = "no_changes_needed"
    coerce_required = "coerce_required"
    s3_complete = "sent_to_s3_complete"
    s3_failed = "sent_to_s3_failed"
    conversion_failed = "failed_data_type_conversion"
