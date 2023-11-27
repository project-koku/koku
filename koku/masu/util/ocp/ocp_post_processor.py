import copy
import json
import logging

import pandas as pd

from api.models import Provider
from masu.processor.ocp.ocp_report_parquet_processor import OCPReportParquetProcessor as trino_schema
from masu.util.common import add_missing_columns_with_dtypes
from masu.util.common import get_column_converters_common
from masu.util.common import populate_enabled_tag_rows_with_false
from masu.util.ocp.common import OCP_REPORT_TYPES

LOG = logging.getLogger(__name__)


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
        return get_column_converters_common(col_names, panda_kwargs, trino_schema, "OCP")

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
        daily_data_frame = add_missing_columns_with_dtypes(daily_data_frame, trino_schema, new_cols)

        return daily_data_frame

    def process_dataframe(self, data_frame):
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
