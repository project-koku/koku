import json
import logging

import pandas

from api.models import Provider
from masu.processor.azure.azure_report_parquet_processor import AzureReportParquetProcessor as trino_schema
from masu.util.azure.common import INGRESS_ALT_COLUMNS
from masu.util.azure.common import INGRESS_REQUIRED_COLUMNS
from masu.util.common import add_missing_columns_with_dtypes
from masu.util.common import get_column_converters_common
from masu.util.common import populate_enabled_tag_rows_with_limit
from masu.util.common import strip_characters_from_column_name
from reporting.provider.azure.models import TRINO_REQUIRED_COLUMNS

LOG = logging.getLogger(__name__)


class AzurePostProcessor:
    def __init__(self, schema):
        self.schema = schema
        self.enabled_tag_keys = set()

    def check_ingress_required_columns(self, col_names):
        """
        Checks the required columns for ingress.
        """
        if not set(col_names).issuperset(INGRESS_REQUIRED_COLUMNS):
            if not set(col_names).issuperset(INGRESS_ALT_COLUMNS):
                missing_columns = [x for x in INGRESS_REQUIRED_COLUMNS if x not in col_names]
                return missing_columns
        return None

    def get_column_converters(self, col_names, panda_kwargs):
        """
        Return source specific parquet column converters.
        """
        return get_column_converters_common(col_names, panda_kwargs, trino_schema, "AZURE")

    def _generate_daily_data(self, data_frame):
        """
        Generate daily data.
        """
        return data_frame

    def process_dataframe(self, data_frame):
        data_frame = add_missing_columns_with_dtypes(data_frame, trino_schema, TRINO_REQUIRED_COLUMNS, True)
        columns = list(data_frame)
        column_name_map = {}

        for column in columns:
            new_col_name = strip_characters_from_column_name(column)
            column_name_map[column] = new_col_name

        data_frame = data_frame.rename(columns=column_name_map)

        columns = set(data_frame)
        columns = set(TRINO_REQUIRED_COLUMNS).union(columns)
        columns = sorted(columns)

        data_frame = data_frame.reindex(columns=columns)

        unique_tags = set()
        for tags_json in data_frame["tags"].values:
            if pandas.notnull(tags_json):
                unique_tags.update(json.loads(tags_json))
        self.enabled_tag_keys.update(unique_tags)
        return data_frame, self._generate_daily_data(data_frame)

    def finalize_post_processing(self):
        """
        Uses information gather in the post processing to update the cost models.
        """
        populate_enabled_tag_rows_with_limit(self.schema, self.enabled_tag_keys, Provider.PROVIDER_AZURE)
