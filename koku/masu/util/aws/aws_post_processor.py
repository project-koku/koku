import json

import ciso8601
import pandas as pd

from masu.util.aws.common import ALL_RESOURCE_TAG_PREFIX
from masu.util.aws.common import COL_TRANSLATION
from masu.util.aws.common import COST_CATEGORY_PREFIX
from masu.util.aws.common import CSV_COLUMN_PREFIX
from masu.util.aws.common import INGRESS_ALT_COLUMNS
from masu.util.aws.common import INGRESS_REQUIRED_COLUMNS
from masu.util.aws.common import RESOURCE_TAG_USER_PREFIX
from masu.util.common import safe_float
from masu.util.common import strip_characters_from_column_name
from masu.util.post_processor import PostProcessor
from reporting.provider.aws.models import AWSEnabledCategoryKeys
from reporting.provider.aws.models import AWSEnabledTagKeys
from reporting.provider.aws.models import TRINO_REQUIRED_COLUMNS


class AWSPostProcessor(PostProcessor):
    def __init__(self, schema):
        super().__init__(schema=schema)
        self.enabled_tag_keys = set()
        self.enabled_categories = set()

    def check_ingress_required_columns(self, col_names):
        """
        Checks the required columns for ingress.
        """
        if not set(col_names).issuperset(INGRESS_REQUIRED_COLUMNS):
            if not set(col_names).issuperset(INGRESS_ALT_COLUMNS):
                missing_columns = [x for x in INGRESS_ALT_COLUMNS if x not in col_names]
                return missing_columns
        return None

    def get_column_converters(self, col_names, panda_kwargs):
        """
        Return source specific parquet column converters.
        """
        converters = {
            "bill/billingperiodstartdate": ciso8601.parse_datetime,
            "bill/billingperiodenddate": ciso8601.parse_datetime,
            "lineitem/usagestartdate": ciso8601.parse_datetime,
            "lineitem/usageenddate": ciso8601.parse_datetime,
            "lineitem/usageamount": safe_float,
            "lineitem/normalizationfactor": safe_float,
            "lineitem/normalizedusageamount": safe_float,
            "lineitem/unblendedrate": safe_float,
            "lineitem/unblendedcost": safe_float,
            "lineitem/blendedrate": safe_float,
            "lineitem/blendedcost": safe_float,
            "pricing/publicondemandcost": safe_float,
            "pricing/publicondemandrate": safe_float,
            "savingsplan/savingsplaneffectivecost": safe_float,
            "bill_billing_period_start_date": ciso8601.parse_datetime,
            "bill_billing_period_end_date": ciso8601.parse_datetime,
            "line_item_usage_start_date": ciso8601.parse_datetime,
            "line_item_usage_end_date": ciso8601.parse_datetime,
            "line_item_usage_amount": safe_float,
            "line_item_normalization_factor": safe_float,
            "line_item_normalized_usage_amount": safe_float,
            "line_item_unblended_rate": safe_float,
            "line_item_unblended_cost": safe_float,
            "line_item_blended_rate": safe_float,
            "line_item_blended_cost": safe_float,
            "pricing_public_on_demand_cost": safe_float,
            "pricing_public_on_demand_rate": safe_float,
            "savings_plan_savings_plan_effective_cost": safe_float,
        }
        csv_converters = {
            col_name: converters[col_name.lower()] for col_name in col_names if col_name.lower() in converters
        }
        csv_converters.update({col: str for col in col_names if col not in csv_converters})
        csv_columns = INGRESS_REQUIRED_COLUMNS + INGRESS_ALT_COLUMNS
        panda_kwargs["usecols"] = [
            col for col in col_names if col in csv_columns or col.startswith(CSV_COLUMN_PREFIX)  # AWS specific
        ]
        return csv_converters, panda_kwargs

    def _generate_daily_data(self, data_frame):
        """
        Generate daily data.
        """
        daily_data_frame = data_frame.groupby(
            [
                "lineitem_resourceid",
                pd.Grouper(key="lineitem_usagestartdate", freq="D"),
                "bill_payeraccountid",
                "lineitem_usageaccountid",
                "lineitem_legalentity",
                "lineitem_lineitemdescription",
                "bill_billingentity",
                "lineitem_productcode",
                "lineitem_availabilityzone",
                "product_productfamily",
                "product_instancetype",
                "product_region",
                "pricing_unit",
                "resourcetags",
                "costcategory",
            ],
            dropna=False,
        ).agg(
            {
                "lineitem_usageamount": ["sum"],
                "lineitem_normalizationfactor": ["max"],
                "lineitem_normalizedusageamount": ["sum"],
                "lineitem_currencycode": ["max"],
                "lineitem_unblendedrate": ["max"],
                "lineitem_unblendedcost": ["sum"],
                "lineitem_blendedrate": ["max"],
                "lineitem_blendedcost": ["sum"],
                "pricing_publicondemandcost": ["sum"],
                "pricing_publicondemandrate": ["max"],
                "savingsplan_savingsplaneffectivecost": ["sum"],
                "product_productname": ["max"],
                "bill_invoiceid": ["max"],
            }
        )
        columns = daily_data_frame.columns.droplevel(1)
        daily_data_frame.columns = columns
        daily_data_frame.reset_index(inplace=True)
        return daily_data_frame

    def process_dataframe(self, data_frame):
        """Process dataframe."""

        def handle_user_defined_json_columns(data_frame, columns, column_prefix):
            """Given a prefix convert multiple dataframe columns into a single json column."""

            def scrub_resource_col_name(res_col_name):
                return res_col_name.replace(column_prefix, "")

            columns_of_interest = [column for column in columns if column_prefix in column]
            unique_keys = {scrub_resource_col_name(column) for column in columns_of_interest}

            df = data_frame[columns_of_interest]
            column_dict = df.apply(
                lambda row: {scrub_resource_col_name(column): value for column, value in row.items() if value}, axis=1
            )
            column_dict.where(column_dict.notna(), lambda _: [{}], inplace=True)

            return column_dict.apply(json.dumps), unique_keys

        org_columns = data_frame.columns.unique()
        columns = []
        for col in org_columns:
            if "/" not in col and COL_TRANSLATION.get(col):
                data_frame = data_frame.rename(columns={col: COL_TRANSLATION[col]})
                columns.append(COL_TRANSLATION[col])
        columns = set(TRINO_REQUIRED_COLUMNS).union(data_frame)
        columns = sorted(list(columns))

        tags, unique_tag_keys = handle_user_defined_json_columns(data_frame, columns, RESOURCE_TAG_USER_PREFIX)
        self.enabled_tag_keys.update(unique_tag_keys)
        data_frame["resourceTags"] = tags

        cost_categories, aws_category_keys = handle_user_defined_json_columns(
            data_frame, columns, COST_CATEGORY_PREFIX
        )
        self.enabled_categories.update(aws_category_keys)
        data_frame["costCategory"] = cost_categories

        # Make sure we have entries for our required columns
        data_frame = data_frame.reindex(columns=columns)

        columns = list(data_frame)
        column_name_map = {}
        drop_columns = []
        for column in columns:
            new_col_name = strip_characters_from_column_name(column)
            column_name_map[column] = new_col_name
            if ALL_RESOURCE_TAG_PREFIX in column or COST_CATEGORY_PREFIX in column:
                drop_columns.append(column)
        data_frame = data_frame.drop(columns=drop_columns)
        data_frame = data_frame.rename(columns=column_name_map)
        return data_frame, self._generate_daily_data(data_frame)

    def finalize_post_processing(self):
        """
        Uses information gather in the
        """
        self.create_enabled_keys(self.enabled_tag_keys, AWSEnabledTagKeys)
        self.create_enabled_keys(self.enabled_categories, AWSEnabledCategoryKeys)
