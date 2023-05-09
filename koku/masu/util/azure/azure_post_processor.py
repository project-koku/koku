import json

import ciso8601
from numpy import nan

from masu.util.azure.common import INGRESS_REQUIRED_COLUMNS
from masu.util.common import safe_float
from masu.util.common import strip_characters_from_column_name
from masu.util.post_processor import PostProcessor
from reporting.provider.azure.models import AzureEnabledTagKeys
from reporting.provider.azure.models import TRINO_COLUMNS


def azure_json_converter(tag_str):
    """Convert either Azure JSON field format to proper JSON."""
    tag_dict = {}
    try:
        if "{" in tag_str:
            tag_dict = json.loads(tag_str)
        else:
            tags = tag_str.split('","')
            for tag in tags:
                key, value = tag.split(": ")
                tag_dict[key.strip('"')] = value.strip('"')
    except (ValueError, TypeError):
        pass

    return json.dumps(tag_dict)


def azure_date_converter(date):
    """Convert Azure date fields properly."""
    if date:
        try:
            new_date = ciso8601.parse_datetime(date)
        except ValueError:
            date_split = date.split("/")
            new_date_str = date_split[2] + date_split[0] + date_split[1]
            new_date = ciso8601.parse_datetime(new_date_str)
        return new_date
    else:
        return nan


class AzurePostProcessor(PostProcessor):
    def __init__(self, schema):
        super().__init__(schema=schema)
        self.enabled_tag_keys = set()

    def check_ingress_required_columns(self, col_names):
        """
        Checks the required columns for ingress.
        """
        if not set(col_names).issuperset(INGRESS_REQUIRED_COLUMNS):
            missing_columns = [x for x in INGRESS_REQUIRED_COLUMNS if x not in col_names]
            return missing_columns
        return None

    def get_column_converters(self, col_names, panda_kwargs):
        """
        Return source specific parquet column converters.
        """
        converters = {
            "usagedatetime": azure_date_converter,
            "date": azure_date_converter,
            "billingperiodstartdate": azure_date_converter,
            "billingperiodenddate": azure_date_converter,
            "usagequantity": safe_float,
            "quantity": safe_float,
            "resourcerate": safe_float,
            "pretaxcost": safe_float,
            "costinbillingcurrency": safe_float,
            "effectiveprice": safe_float,
            "unitprice": safe_float,
            "paygprice": safe_float,
            "tags": azure_json_converter,
            "additionalinfo": azure_json_converter,
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
        return data_frame

    def process_dataframe(self, data_frame):
        columns = list(data_frame)
        column_name_map = {}

        for column in columns:
            new_col_name = strip_characters_from_column_name(column)
            column_name_map[column] = new_col_name

        data_frame = data_frame.rename(columns=column_name_map)

        columns = set(data_frame)
        columns = set(TRINO_COLUMNS).union(columns)
        columns = sorted(columns)

        data_frame = data_frame.reindex(columns=columns)

        unique_tags = set()
        for tags_json in data_frame["tags"]:
            unique_tags.update(json.loads(tags_json))
        self.enabled_tag_keys.update(unique_tags)
        return data_frame, self._generate_daily_data(data_frame)

    def finalize_post_processing(self):
        """
        Uses information gather in the post processing to update the cost models.
        """
        self.create_enabled_keys(self.enabled_tag_keys, AzureEnabledTagKeys)
