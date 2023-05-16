import json

import ciso8601
import pandas as pd

from masu.util.common import create_enabled_keys
from masu.util.common import safe_float
from masu.util.common import strip_characters_from_column_name
from reporting.provider.oci.models import OCIEnabledTagKeys
from reporting.provider.oci.models import TRINO_REQUIRED_COLUMNS


def scrub_resource_col_name(res_col_name):
    return res_col_name.split(".")[-1]


class OCIPostProcessor:
    def __init__(self, schema):
        self.schema = schema
        self.enabled_tag_keys = set()

    def get_column_converters(self, col_names, panda_kwargs):
        """
        Return source specific parquet column converters.
        """
        converters = {
            "bill/billingperiodstartdate": ciso8601.parse_datetime,
            "bill/billingperiodenddate": ciso8601.parse_datetime,
            "lineitem/intervalusagestart": ciso8601.parse_datetime,
            "lineitem/intervalusageend": ciso8601.parse_datetime,
            "usage/consumedquantity": safe_float,
            "cost/mycost": safe_float,
        }
        csv_converters = {
            col_name: converters[col_name.lower()] for col_name in col_names if col_name.lower() in converters
        }
        csv_converters.update({col: str for col in col_names if col not in csv_converters})
        return csv_converters, panda_kwargs

    def check_ingress_required_columns(self, _):
        """
        Checks the required columns for ingress.
        """
        return None

    def _generate_daily_data(self, data_frame):
        """Given a dataframe, group the data to create daily data."""

        if "cost_mycost" in data_frame:
            daily_data_frame = data_frame.groupby(
                [
                    "product_resourceid",
                    pd.Grouper(key="lineitem_intervalusagestart", freq="D"),
                    "lineitem_tenantid",
                    "product_service",
                    "product_region",
                    "tags",
                ],
                dropna=False,
            ).agg({"cost_currencycode": ["max"], "cost_mycost": ["sum"]})
        else:
            daily_data_frame = data_frame.groupby(
                [
                    "product_resourceid",
                    pd.Grouper(key="lineitem_intervalusagestart", freq="D"),
                    "lineitem_tenantid",
                    "product_service",
                    "product_region",
                    "tags",
                ],
                dropna=False,
            ).agg({"usage_consumedquantity": ["sum"]})
        columns = daily_data_frame.columns.droplevel(1)
        daily_data_frame.columns = columns
        daily_data_frame.reset_index(inplace=True)

        return daily_data_frame

    def process_dataframe(self, data_frame):
        """
        Consume the OCI data and add a column creating a dictionary for the oci tags
        """

        columns = set(list(data_frame))
        columns = set(TRINO_REQUIRED_COLUMNS).union(columns)
        columns = sorted(list(columns))

        resource_tag_columns = [column for column in columns if "tags/" in column]
        unique_keys = {scrub_resource_col_name(column) for column in resource_tag_columns}
        self.enabled_tag_keys.update(unique_keys)
        tag_df = data_frame[resource_tag_columns]
        resource_tags_dict = tag_df.apply(
            lambda row: {scrub_resource_col_name(column): value for column, value in row.items() if value}, axis=1
        )
        resource_tags_dict.where(resource_tags_dict.notna(), lambda _: [{}], inplace=True)

        data_frame["tags"] = resource_tags_dict.apply(json.dumps)
        # Make sure we have entries for our required columns
        data_frame = data_frame.reindex(columns=columns)

        columns = list(data_frame)
        column_name_map = {}
        drop_columns = []
        for column in columns:
            new_col_name = strip_characters_from_column_name(column)
            column_name_map[column] = new_col_name
            if "tags/" in column:
                drop_columns.append(column)
        data_frame = data_frame.drop(columns=drop_columns)
        data_frame = data_frame.rename(columns=column_name_map)
        return data_frame, self._generate_daily_data(data_frame)

    def finalize_post_processing(self):
        """
        Uses information gather in the post processing to update the cost models.
        """
        create_enabled_keys(self.schema, OCIEnabledTagKeys, self.enabled_tag_keys)
