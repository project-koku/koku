import json
import logging
from json.decoder import JSONDecodeError
from uuid import uuid4

import ciso8601
import pandas as pd

from api.models import Provider
from masu.processor import is_gcp_credits_in_json
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
            "credits.amount": safe_float,
            "credits": process_gcp_credits, # This is needed to support OG filter flow temperarily
        }
        csv_converters = {
            col_name: converters[col_name.lower()] for col_name in col_names if col_name.lower() in converters
        }
        csv_converters.update({col: str for col in col_names if col not in csv_converters})
        return csv_converters, panda_kwargs

    def _generate_daily_data(self, data_frame):
        """
        Generate daily data.
        """
        """Given a dataframe, return the data frame if its empty, group the data to create daily data."""
        if data_frame.empty:
            return data_frame

        rollup_frame = data_frame.copy()
        if is_gcp_credits_in_json(self.schema):
            # this parses the credits column into just the dollar amount so we can sum it up for daily rollups
            # We need this flag to support filter flow until customers move away from credits as json
            rollup_frame["credits"] = rollup_frame["credits"].apply(json.loads)
            rollup_frame["credits_amount"] = rollup_frame["credits"].apply(lambda x: x.get("amount") or 0.0)
            rollup_frame["daily_credits"] = rollup_frame["credits"].apply(lambda x: x.get("amount") or 0.0)
        else:
            # We need to populate old and new column for 3 months before removing old column
            rollup_frame["daily_credits"] = rollup_frame["credits_amount"]

        resource_df = rollup_frame.get("resource_name")
        try:
            if not resource_df:
                rollup_frame["resource_name"] = ""
                rollup_frame["resource_global_name"] = ""
        except Exception:
            if not resource_df.any():
                rollup_frame["resource_name"] = ""
                rollup_frame["resource_global_name"] = ""
        daily_data_frame = rollup_frame.groupby(
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
                "credits_amount": ["sum"],
                "resource_global_name": ["max"],
            }
        )
        columns = daily_data_frame.columns.droplevel(1)
        daily_data_frame.columns = columns
        daily_data_frame.reset_index(inplace=True)

        # Add a unique identifer that we can use for deduplicating
        daily_data_frame["row_uuid"] = [str(uuid4()) for _ in range(len(daily_data_frame))]
        return daily_data_frame

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
