import copy
import json
import logging

import ciso8601
import pandas as pd
from dateutil.parser import ParserError

from masu.util.common import create_enabled_keys
from masu.util.common import safe_float
from masu.util.ocp.common import OCP_REPORT_TYPES
from reporting.provider.ocp.models import OCPEnabledTagKeys

LOG = logging.getLogger(__name__)


def process_openshift_datetime(val):
    """
    Convert the date time from the Metering operator reports to a consumable datetime.
    """
    result = None
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

    def check_ingress_required_columns(self, col_names):
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
            "pod_labels": process_openshift_labels_to_json,
            "persistentvolume_labels": process_openshift_labels_to_json,
            "persistentvolumeclaim_labels": process_openshift_labels_to_json,
            "node_labels": process_openshift_labels_to_json,
            "namespace_labels": process_openshift_labels_to_json,
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

        report = self.ocp_report_types.get(self.report_type, {})
        group_bys = copy.deepcopy(report.get("group_by", []))
        group_bys.append(pd.Grouper(key="interval_start", freq="D"))
        aggs = report.get("agg", {})
        daily_data_frame = data_frame.groupby(group_bys, dropna=False).agg(
            {k: v for k, v in aggs.items() if k in data_frame.columns}
        )

        columns = daily_data_frame.columns.droplevel(1)
        daily_data_frame.columns = columns

        daily_data_frame.reset_index(inplace=True)

        new_cols = report.get("new_required_columns")
        for col in new_cols:
            if col not in daily_data_frame:
                daily_data_frame[col] = None

        return daily_data_frame

    def process_dataframe(self, data_frame):
        label_columns = {"pod_labels", "volume_labels", "namespace_labels", "node_labels"}
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
        create_enabled_keys(self.schema, OCPEnabledTagKeys, self.enabled_tag_keys)
