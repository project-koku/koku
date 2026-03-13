import json
import logging

import ciso8601
import pandas as pd
from dateutil.parser import ParserError

from api.common import log_json
from api.models import Provider
from masu.util.common import populate_enabled_tag_rows_with_false
from masu.util.common import safe_float
from masu.util.common import safe_float_or_none
from masu.util.common import safe_int_or_none
from masu.util.ocp.common import GPU_MAX_SLICES_BY_MODEL
from masu.util.ocp.common import OCP_REPORT_TYPES
from masu.util.ocp.common import THRESHOLDS

LOG = logging.getLogger(__name__)


def parse_mig_profile(profile: str | None) -> tuple[int | None, int | None]:
    """Parse a MIG profile string to extract slice count and memory in MiB.

    MIG profile format: "{compute}g.{memory}gb" (e.g., "1g.5gb", "4g.40gb")

    Args:
        profile: MIG profile string (e.g., "1g.5gb", "4g.40gb")

    Returns:
        Tuple of (slice_count, memory_mib) or (None, None) if profile is invalid/empty
    """
    if not profile or not isinstance(profile, str):
        return None, None

    profile = profile.strip().lower()
    if not profile:
        return None, None

    try:
        # Format: {compute}g.{memory}gb
        parts = profile.split(".")
        if len(parts) != 2:
            LOG.warning(f"Invalid MIG profile format: {profile}")
            return None, None

        compute_part = parts[0]  # e.g., "1g", "4g"
        memory_part = parts[1]  # e.g., "5gb", "40gb"

        # Extract slice count from compute part (remove 'g' suffix)
        if not compute_part.endswith("g"):
            LOG.warning(f"Invalid MIG profile compute part: {compute_part}")
            return None, None
        slice_count = int(compute_part[:-1])

        # Extract memory from memory part (remove 'gb' suffix)
        if not memory_part.endswith("gb"):
            LOG.warning(f"Invalid MIG profile memory part: {memory_part}")
            return None, None
        memory_gb = int(memory_part[:-2])
        memory_mib = memory_gb * 1024  # Convert GB to MiB

        return slice_count, memory_mib
    except (ValueError, IndexError) as e:
        LOG.warning(f"Failed to parse MIG profile '{profile}': {e}")
        return None, None


def get_gpu_max_slices(gpu_model: str | None) -> int | None:
    """Get the maximum number of MIG slices for a GPU model.

    Args:
        gpu_model: GPU model name (e.g., "A100", "H100")

    Returns:
        Maximum number of slices for the GPU model, or None if model is unrecognized
        (MIG fields should be cleared and GPU treated as dedicated).
    """
    if not gpu_model:
        return None

    # Normalize model name for lookup
    model_upper = gpu_model.upper().strip()

    # Try exact match first
    if model_upper in GPU_MAX_SLICES_BY_MODEL:
        return GPU_MAX_SLICES_BY_MODEL[model_upper]

    # Try partial match (e.g., "NVIDIA A100-80GB-PCIe" should match "A100")
    for known_model, max_slices in GPU_MAX_SLICES_BY_MODEL.items():
        if known_model in model_upper:
            return max_slices

    # Unknown model - return None to indicate MIG fields should be cleared
    LOG.warning(
        f"GPU model '{gpu_model}' not found in MIG max slices mapping and no observed data. "
        f"MIG data will be cleared and GPU will be treated as dedicated."
    )
    return None


def process_openshift_datetime(val):
    """
    Convert the date time from the Metering operator reports to a consumable datetime.
    """
    result = pd.NaT
    try:
        datetime_str = str(val).replace(" +0000 UTC", "")
        result = ciso8601.parse_datetime(datetime_str)
    except ParserError:
        pass
    return result


def process_openshift_labels(label_string):
    """Convert the report string to a JSON dictionary.

    Args:
        label_string (str): The raw report string of pod labels

    Returns:
        (dict): The JSON dictionary made from the label string

    Dev Note:
        You can reference the operator here to see what queries to run
        in prometheus to see the labels.

    """
    labels = label_string.split("|") if label_string else []
    label_dict = {}

    for label in labels:
        if ":" not in label:
            continue
        try:
            key, value = label.split(":")
            key = key.replace("label_", "")
            label_dict[key] = value
        except ValueError as err:
            LOG.warning(err)
            LOG.warning("%s could not be properly split", label)
            continue
    return label_dict


def process_openshift_labels_to_json(label_val):
    return json.dumps(process_openshift_labels(label_val))


class OCPPostProcessor:
    def __init__(self, schema, report_type):
        self.schema = schema
        self.enabled_tag_keys = set()
        self.report_type = report_type
        self.ocp_report_types = OCP_REPORT_TYPES

    def __add_effective_usage_columns(self, data_frame):
        """Add effective usage columns to pod data frame."""
        if self.report_type != "pod_usage":
            return data_frame
        data_frame["pod_effective_usage_cpu_core_seconds"] = data_frame[
            ["pod_usage_cpu_core_seconds", "pod_request_cpu_core_seconds"]
        ].max(axis=1)
        data_frame["pod_effective_usage_memory_byte_seconds"] = data_frame[
            ["pod_usage_memory_byte_seconds", "pod_request_memory_byte_seconds"]
        ].max(axis=1)
        return data_frame

    def check_ingress_required_columns(self, _):
        """
        Checks the required columns for ingress.
        """
        return None

    def get_column_converters(self, col_names, panda_kwargs):
        """
        Return source specific parquet column converters.
        """
        converters = {
            "report_period_start": process_openshift_datetime,
            "report_period_end": process_openshift_datetime,
            "interval_start": process_openshift_datetime,
            "interval_end": process_openshift_datetime,
            "pod_usage_cpu_core_seconds": safe_float,
            "pod_request_cpu_core_seconds": safe_float,
            "pod_limit_cpu_core_seconds": safe_float,
            "pod_usage_memory_byte_seconds": safe_float,
            "pod_request_memory_byte_seconds": safe_float,
            "pod_limit_memory_byte_seconds": safe_float,
            "node_capacity_cpu_cores": safe_float,
            "node_capacity_cpu_core_seconds": safe_float,
            "node_capacity_memory_bytes": safe_float,
            "node_capacity_memory_byte_seconds": safe_float,
            "persistentvolumeclaim_capacity_bytes": safe_float,
            "persistentvolumeclaim_capacity_byte_seconds": safe_float,
            "volume_request_storage_byte_seconds": safe_float,
            "persistentvolumeclaim_usage_byte_seconds": safe_float,
            "vm_uptime_total_seconds": safe_float,
            "vm_cpu_limit_cores": safe_float,
            "vm_cpu_limit_core_seconds": safe_float,
            "vm_cpu_request_cores": safe_float,
            "vm_cpu_request_core_seconds": safe_float,
            "vm_cpu_request_sockets": safe_float,
            "vm_cpu_request_socket_seconds": safe_float,
            "vm_cpu_request_threads": safe_float,
            "vm_cpu_request_thread_seconds": safe_float,
            "vm_cpu_usage_total_seconds": safe_float,
            "vm_memory_limit_bytes": safe_float,
            "vm_memory_limit_byte_seconds": safe_float,
            "vm_memory_request_bytes": safe_float,
            "vm_memory_request_byte_seconds": safe_float,
            "vm_memory_usage_byte_seconds": safe_float,
            "vm_disk_allocated_size_byte_seconds": safe_float,
            "gpu_memory_capacity_mib": safe_float,
            "gpu_pod_uptime": safe_float,
            # MIG fields - convert empty strings to None for nullable columns
            "mig_slice_count": safe_int_or_none,
            "parent_gpu_max_slices": safe_int_or_none,
            "mig_memory_capacity_mib": safe_float_or_none,
            "pod_labels": process_openshift_labels_to_json,
            "persistentvolume_labels": process_openshift_labels_to_json,
            "persistentvolumeclaim_labels": process_openshift_labels_to_json,
            "node_labels": process_openshift_labels_to_json,
            "namespace_labels": process_openshift_labels_to_json,
            "vm_labels": process_openshift_labels_to_json,
        }
        csv_converters = {
            col_name: converters[col_name.lower()] for col_name in col_names if col_name.lower() in converters
        }
        csv_converters.update({col: str for col in col_names if col not in csv_converters})
        return csv_converters, panda_kwargs

    def _generate_daily_data(self, data_frame):
        """Given a dataframe, group the data to create daily data."""

        data_frame = self.__add_effective_usage_columns(data_frame)

        if data_frame.empty:
            return data_frame

        report = self.ocp_report_types[self.report_type]
        group_bys = [gb for gb in report["group_by"] if gb in data_frame.columns]
        group_bys.append(pd.Grouper(key="interval_start", freq="D"))
        aggs = {k: v for k, v in report["agg"].items() if k in data_frame.columns}
        daily_data_frame = data_frame.groupby(group_bys, dropna=False).agg(aggs)

        columns = daily_data_frame.columns.droplevel(1)
        daily_data_frame.columns = columns

        daily_data_frame = daily_data_frame.reset_index()

        for col, dtype in report["new_required_columns"].items():
            if col not in daily_data_frame:
                daily_data_frame[col] = pd.Series(dtype=dtype)

        return daily_data_frame

    def _remove_anomalies(self, data_frame: pd.DataFrame, filename: str) -> pd.DataFrame:
        """Removes rows with anomalous values from the DataFrame."""

        # only consider existing cols
        common = data_frame.columns.intersection(THRESHOLDS)
        # build boolean mask of any col > its threshold
        mask = data_frame[common].gt(pd.Series(THRESHOLDS)).any(axis=1)

        if mask.any():
            LOG.warning(log_json(msg="Dropping anomalous rows", schema=self.schema, filename=filename))

        return data_frame.loc[~mask]

    def _ensure_mig_columns(self, data_frame):
        """Ensure MIG-related columns exist in the dataframe."""
        for col in ("mig_slice_count", "mig_memory_capacity_mib", "parent_gpu_max_slices"):
            if col not in data_frame.columns:
                data_frame[col] = pd.NA
        return data_frame

    def _parse_mig_profile_for_rows(self, data_frame, has_mig_data):
        """Parse MIG profiles to populate slice count and memory for rows missing these values."""
        for idx in data_frame[has_mig_data].index:
            profile = data_frame.at[idx, "mig_profile"]
            slice_count, memory_mib = parse_mig_profile(profile)

            if pd.isna(data_frame.at[idx, "mig_slice_count"]) and slice_count is not None:
                data_frame.at[idx, "mig_slice_count"] = slice_count

            if pd.isna(data_frame.at[idx, "mig_memory_capacity_mib"]) and memory_mib is not None:
                data_frame.at[idx, "mig_memory_capacity_mib"] = memory_mib

    def _clear_mig_fields_for_row(self, data_frame, idx):
        """Clear all MIG fields for a row, treating it as a dedicated GPU."""
        data_frame.at[idx, "mig_profile"] = pd.NA
        data_frame.at[idx, "mig_slice_count"] = pd.NA
        data_frame.at[idx, "mig_memory_capacity_mib"] = pd.NA
        data_frame.at[idx, "parent_gpu_max_slices"] = pd.NA
        if "mig_instance_id" in data_frame.columns:
            data_frame.at[idx, "mig_instance_id"] = pd.NA

    def _populate_mig_fields_from_profile(self, data_frame):
        """Populate MIG fields (mig_memory_capacity_mib, parent_gpu_max_slices) from mig_profile.

        The operator may not provide these fields directly, so we derive them:
        - mig_memory_capacity_mib: parsed from mig_profile (e.g., "1g.5gb" -> 5120 MiB)
        - parent_gpu_max_slices: looked up from GPU model, or computed from sum of slice counts
        - mig_slice_count: parsed from mig_profile if not present (e.g., "1g.5gb" -> 1)

        If the GPU model is unknown and we cannot determine max_slices, all MIG fields are
        cleared and the GPU is treated as dedicated.
        """
        if self.report_type != "gpu_usage" or "mig_profile" not in data_frame.columns:
            return data_frame

        has_mig_data = data_frame["mig_profile"].notna() & (data_frame["mig_profile"] != "")
        if not has_mig_data.any():
            return data_frame

        data_frame = self._ensure_mig_columns(data_frame)
        self._parse_mig_profile_for_rows(data_frame, has_mig_data)

        # Populate parent_gpu_max_slices or clear MIG fields for unknown models
        for idx in data_frame[has_mig_data].index:
            if not pd.isna(data_frame.at[idx, "parent_gpu_max_slices"]):
                continue

            gpu_model = data_frame.at[idx, "gpu_model_name"] if "gpu_model_name" in data_frame.columns else None
            max_slices = get_gpu_max_slices(gpu_model)

            if max_slices is None:
                self._clear_mig_fields_for_row(data_frame, idx)
            else:
                data_frame.at[idx, "parent_gpu_max_slices"] = max_slices

        return data_frame

    def process_dataframe(self, data_frame, filename):
        data_frame = self._remove_anomalies(data_frame, filename)
        label_columns = {
            "pod_labels",
            "persistentvolume_labels",
            "persistentvolumeclaim_labels",
            "namespace_labels",
            "node_labels",
        }
        df_columns = set(data_frame.columns)
        columns_to_grab = df_columns.intersection(label_columns)
        label_key_set = set()
        for column in columns_to_grab:
            unique_labels = data_frame[column].unique()
            for label in unique_labels:
                label_key_set.update(json.loads(label).keys())
        gpu_column = "gpu_vendor_name"
        if gpu_column in data_frame.columns:
            data_frame[gpu_column] = data_frame[gpu_column].replace("nvidia_com_gpu", "nvidia")
        self.enabled_tag_keys.update(label_key_set)

        # Populate MIG fields from profile for GPU reports
        data_frame = self._populate_mig_fields_from_profile(data_frame)

        return data_frame, self._generate_daily_data(data_frame)

    def finalize_post_processing(self):
        """
        Uses information gather in the post processing to update the cost models.
        """
        populate_enabled_tag_rows_with_false(self.schema, self.enabled_tag_keys, Provider.PROVIDER_OCP)
