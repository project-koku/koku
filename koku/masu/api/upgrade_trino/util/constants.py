from enum import Enum

# Update this to trigger the converter to run again
# even if marked as successful
CONVERTER_VERSION = "1"


class ReprEnum(Enum):
    """
    Only changes the repr(), leaving str() and format() to the mixed-in type.
    """


# StrEnum is available in python 3.11, vendored over from
# https://github.com/python/cpython/blob/c31be58da8577ef140e83d4e46502c7bb1eb9abf/Lib/enum.py#L1321-L1345
class StrEnum(str, ReprEnum):  # pragma: no cover
    """
    Enum where members are also (and must be) strings
    """

    def __new__(cls, *values):
        "values must already be of type `str`"
        if len(values) > 3:
            raise TypeError(f"too many arguments for str(): {values!r}")
        if len(values) == 1:
            # it must be a string
            if not isinstance(values[0], str):
                raise TypeError(f"{values[0]!r} is not a string")
        if len(values) >= 2:
            # check that encoding argument is a string
            if not isinstance(values[1], str):
                raise TypeError(f"encoding must be a string, not {values[1]!r}")
        if len(values) == 3:
            # check that errors argument is a string
            if not isinstance(values[2], str):
                raise TypeError("errors must be a string, not %r" % (values[2]))
        value = str(*values)
        member = str.__new__(cls, value)
        member._value_ = value
        return member


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
