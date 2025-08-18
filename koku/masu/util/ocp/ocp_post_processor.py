import json
import logging

import ciso8601
import pandas as pd
from dateutil.parser import ParserError

from api.common import log_json
from api.models import Provider
from masu.util.common import populate_enabled_tag_rows_with_false
from masu.util.common import safe_float
from masu.util.ocp.common import OCP_REPORT_TYPES

LOG = logging.getLogger(__name__)


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

        threshold_map = {
            # 1,000,000,000,000,000,000 is a resonable value that should remove most anomlies from bad data
            1e18: [
                "pod_usage_cpu_core_seconds",
                "pod_request_cpu_core_seconds",
                "pod_limit_cpu_core_seconds",
                "node_capacity_cpu_core_seconds",
                "pod_usage_memory_byte_seconds",
                "pod_request_memory_byte_seconds",
                "pod_limit_memory_byte_seconds",
                "node_capacity_memory_byte_seconds",
                "node_capacity_memory_bytes",
                "persistentvolumeclaim_capacity_bytes",
                "persistentvolumeclaim_capacity_byte_seconds",
                "volume_request_storage_byte_seconds",
                "persistentvolumeclaim_usage_byte_seconds",
            ],
        }
        thresholds = {col: thresh for thresh, cols in threshold_map.items() for col in cols}

        # only consider existing cols
        common = data_frame.columns.intersection(thresholds)
        # build boolean mask of any col > its threshold
        mask = data_frame[common].gt(pd.Series(thresholds)).any(axis=1)

        if mask.any():
            LOG.warning(log_json(msg="Dropping anomalous rows", schema=self.schema, filename=filename))

        return data_frame.loc[~mask]

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
        self.enabled_tag_keys.update(label_key_set)
        return data_frame, self._generate_daily_data(data_frame)

    def finalize_post_processing(self):
        """
        Uses information gather in the post processing to update the cost models.
        """
        populate_enabled_tag_rows_with_false(self.schema, self.enabled_tag_keys, Provider.PROVIDER_OCP)
