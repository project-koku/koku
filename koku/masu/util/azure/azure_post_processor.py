import json
import logging
from uuid import uuid4

import ciso8601
import pandas as pd

from api.models import Provider
from masu.util.azure.common import INGRESS_REQUIRED_ALT_COLUMNS
from masu.util.azure.common import INGRESS_REQUIRED_COLUMNS
from masu.util.common import populate_enabled_tag_rows_with_limit
from masu.util.common import safe_float
from masu.util.common import strip_characters_from_column_name
from reporting.provider.azure.models import TRINO_REQUIRED_COLUMNS

LOG = logging.getLogger(__name__)


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
        return pd.NaT


class AzurePostProcessor:
    def __init__(self, schema):
        self.schema = schema
        self.enabled_tag_keys = set()

    # Different Azure Cost Exports can have different fields,
    # this maps some column names to expected names for consistency with TRINO_REQUIRED_COLUMNS
    COL_TRANSLATION = {
        "resourcegroupname": "resourcegroup",
        "instancename": "resourceid",
        "product": "productname",
    }

    def check_ingress_required_columns(self, col_names):
        """
        Checks the required columns for ingress.
        """
        lower_columns = [x.lower() for x in col_names]
        missing_columns = [x for x in INGRESS_REQUIRED_COLUMNS if x not in lower_columns]
        for alternative_set in INGRESS_REQUIRED_ALT_COLUMNS:
            if not any(x in lower_columns for x in alternative_set):
                missing_columns.append(alternative_set[0])

        if missing_columns != []:
            return missing_columns
        return None

    def get_column_converters(self, col_names, panda_kwargs):
        """
        Return source specific parquet column converters.
        """
        converters = {
            "date": azure_date_converter,
            "billingperiodstartdate": azure_date_converter,
            "billingperiodenddate": azure_date_converter,
            "quantity": safe_float,
            "resourcerate": safe_float,
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
            new_col_name = self.COL_TRANSLATION.get(new_col_name, new_col_name)
            column_name_map[column] = new_col_name

        data_frame = data_frame.rename(columns=column_name_map)

        missing = set(TRINO_REQUIRED_COLUMNS).difference(data_frame)
        to_add = {k: TRINO_REQUIRED_COLUMNS[k] for k in missing}
        data_frame = data_frame.assign(**to_add)

        unique_tags = set()
        for tags_json in data_frame["tags"].values:
            if pd.notnull(tags_json):
                unique_tags.update(json.loads(tags_json))
        self.enabled_tag_keys.update(unique_tags)
        # Add a unique identifer that we can use for deduplicating
        data_frame["row_uuid"] = data_frame.apply(lambda _: str(uuid4()), axis=1)
        return data_frame, self._generate_daily_data(data_frame)

    def finalize_post_processing(self):
        """
        Uses information gather in the post processing to update the cost models.
        """
        populate_enabled_tag_rows_with_limit(self.schema, self.enabled_tag_keys, Provider.PROVIDER_AZURE)
