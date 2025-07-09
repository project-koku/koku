import json
import logging
from json.decoder import JSONDecodeError
from uuid import uuid4

import ciso8601
import pandas as pd

from api.models import Provider
from masu.util.common import populate_enabled_tag_rows_with_false
from masu.util.common import safe_float
from masu.util.common import strip_characters_from_column_name

LOG = logging.getLogger(__name__)


def process_gcp_labels(label_string):
    """Convert the report string to a JSON dictionary.

    Args:
        label_string (str): The raw report string of pod labels

    Returns:
        (dict): The JSON dictionary made from the label string

    """
    label_dict = {}
    try:
        if label_string:
            labels = json.loads(label_string)
            label_dict = {entry.get("key"): entry.get("value") for entry in labels}
    except JSONDecodeError:
        LOG.warning("Unable to process GCP labels.")

    return json.dumps(label_dict)


def process_gcp_credits(credit_string: str) -> str:
    """Process the credits column

    This should be a valid JSON string that can be deserialized.

    """
    credit_dict = {}
    gcp_credits = None
    try:
        gcp_credits = json.loads(credit_string)
    except JSONDecodeError:
        # Fall back in case the string is a struct and not valid JSON
        try:
            gcp_credits = json.loads(credit_string.replace("'", '"').replace("None", '"None"'))
        except JSONDecodeError as err:
            LOG.warning(f"Unable to process GCP credits: {err}")

    if gcp_credits:
        credit_dict = gcp_credits[0]

    return json.dumps(credit_dict)


class GCPPostProcessor:
    INGRESS_REQUIRED_COLUMNS = {
        "billing_account_id",
        "service.id",
        "service.description",
        "sku.id",
        "sku.description",
        "usage_start_time",
        "usage_end_time",
        "project.id",
        "project.name",
        "project.ancestry_numbers",
        "location.location",
        "location.country",
        "location.region",
        "location.zone",
        "export_time",
        "cost",
        "currency",
        "currency_conversion_rate",
        "usage.amount",
        "usage.unit",
        "usage.amount_in_pricing_units",
        "usage.pricing_unit",
        "credits",
        "invoice.month",
        "cost_type",
        "partition_date",
    }

    def __init__(self, schema):
        self.schema = schema
        self.enabled_tag_keys = set()

    def check_ingress_required_columns(self, col_names):
        """
        Checks the required columns for ingress.
        """
        if not set(col_names).issuperset(self.INGRESS_REQUIRED_COLUMNS):
            missing_columns = [x for x in self.INGRESS_REQUIRED_COLUMNS if x not in col_names]
            return missing_columns
        return None

    def get_column_converters(self, col_names, panda_kwargs):
        """
        Return source specific parquet column converters.
        """
        converters = {
            "usage_start_time": ciso8601.parse_datetime,
            "usage_end_time": ciso8601.parse_datetime,
            "project.labels": process_gcp_labels,
            "labels": process_gcp_labels,
            "system_labels": process_gcp_labels,
            "export_time": ciso8601.parse_datetime,
            "cost": safe_float,
            "currency_conversion_rate": safe_float,
            "usage.amount": safe_float,
            "usage.amount_in_pricing_units": safe_float,
            "credits": process_gcp_credits,
        }
        csv_converters = {
            col_name: converters[col_name.lower()] for col_name in col_names if col_name.lower() in converters
        }
        csv_converters.update({col: str for col in col_names if col not in csv_converters})
        return csv_converters, panda_kwargs

    def _generate_daily_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate daily data.
        """
        """Given a dataframe, return the data frame if its empty, group the data to create daily data."""
        if df.empty:
            return df

        # this parses the credits column into just the dollar amount so we can sum it up for daily rollups
        daily_df = df.copy()
        daily_df["daily_credits"] = daily_df["credits"].apply(lambda x: json.loads(x).get("amount") or 0.0)
        if "resource_name" not in daily_df.columns:
            daily_df["resource_name"] = ""
            daily_df["resource_global_name"] = ""
        daily_df = daily_df.groupby(
            [
                "invoice_month",
                "billing_account_id",
                "project_id",
                pd.Grouper(key="usage_start_time", freq="D"),
                "service_id",
                "sku_id",
                "system_labels",
                "labels",
                "cost_type",
                "location_region",
                "resource_name",
            ],
            dropna=False,
        ).agg(
            {
                "project_name": ["max"],
                "service_description": ["max"],
                "sku_description": ["max"],
                "usage_pricing_unit": ["max"],
                "usage_amount_in_pricing_units": ["sum"],
                "currency": ["max"],
                "cost": ["sum"],
                "daily_credits": ["sum"],
                "resource_global_name": ["max"],
            }
        )
        columns = daily_df.columns.droplevel(1)
        daily_df.columns = columns
        daily_df = daily_df.reset_index()

        # Add a unique identifer that we can use for deduplicating
        daily_df["row_uuid"] = daily_df.apply(lambda _: str(uuid4()), axis=1)
        return daily_df

    def process_dataframe(self, data_frame):
        """Guarantee column order for GCP parquet files"""
        columns = list(data_frame)
        column_name_map = {}
        for column in columns:
            new_col_name = strip_characters_from_column_name(column)
            column_name_map[column] = new_col_name
        data_frame = data_frame.rename(columns=column_name_map)
        label_set = set()
        unique_labels = data_frame.labels.unique()
        for label in unique_labels:
            label_set.update(json.loads(label).keys())
        self.enabled_tag_keys.update(label_set)

        return data_frame, self._generate_daily_data(data_frame)

    def finalize_post_processing(self):
        """
        Uses information gather in the post processing to update the cost models.
        """
        populate_enabled_tag_rows_with_false(self.schema, self.enabled_tag_keys, Provider.PROVIDER_GCP)
