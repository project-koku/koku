import json

import ciso8601
import pandas as pd

from masu.util.common import create_enabled_keys
from masu.util.common import safe_float
from masu.util.common import strip_characters_from_column_name
from reporting.provider.aws.models import AWSEnabledCategoryKeys
from reporting.provider.aws.models import AWSEnabledTagKeys
from reporting.provider.aws.models import TRINO_REQUIRED_COLUMNS


def scrub_resource_col_name(res_col_name, column_prefix):
    return res_col_name.replace(column_prefix, "")


def handle_user_defined_json_columns(data_frame, columns, column_prefix):
    """Given a prefix convert multiple dataframe columns into a single json column."""

    columns_of_interest = [column for column in columns if column_prefix in column]
    unique_keys = {scrub_resource_col_name(column, column_prefix) for column in columns_of_interest}

    df = data_frame[columns_of_interest]
    column_dict = df.apply(
        lambda row: {scrub_resource_col_name(column, column_prefix): value for column, value in row.items() if value},
        axis=1,
    )
    column_dict.where(column_dict.notna(), lambda _: [{}], inplace=True)

    return column_dict.apply(json.dumps), unique_keys


class AWSPostProcessor:

    PRODUCT_SKU_COL = "product/sku"  # removes code smell
    ALL_RESOURCE_TAG_PREFIX = "resourceTags/"
    RESOURCE_TAG_USER_PREFIX = "resourceTags/user:"
    COST_CATEGORY_PREFIX = "costCategory/"

    INGRESS_REQUIRED_COLUMNS = {
        "bill/BillingEntity",
        "bill/BillType",
        "bill/PayerAccountId",
        "bill/BillingPeriodStartDate",
        "bill/BillingPeriodEndDate",
        "bill/InvoiceId",
        "lineItem/LineItemType",
        "lineItem/UsageAccountId",
        "lineItem/UsageStartDate",
        "lineItem/UsageEndDate",
        "lineItem/ProductCode",
        "lineItem/UsageType",
        "lineItem/Operation",
        "lineItem/AvailabilityZone",
        "lineItem/ResourceId",
        "lineItem/UsageAmount",
        "lineItem/NormalizationFactor",
        "lineItem/NormalizedUsageAmount",
        "lineItem/CurrencyCode",
        "lineItem/UnblendedRate",
        "lineItem/UnblendedCost",
        "lineItem/BlendedRate",
        "lineItem/BlendedCost",
        "savingsPlan/SavingsPlanEffectiveCost",
        "lineItem/TaxType",
        "pricing/publicOnDemandCost",
        "pricing/publicOnDemandRate",
        "reservation/AmortizedUpfrontFeeForBillingPeriod",
        "reservation/AmortizedUpfrontCostForUsage",
        "reservation/RecurringFeeForUsage",
        "reservation/UnusedQuantity",
        "reservation/UnusedRecurringFee",
        "pricing/term",
        "pricing/unit",
        PRODUCT_SKU_COL,
        "product/ProductName",
        "product/productFamily",
        "product/servicecode",
        "product/region",
        "product/instanceType",
        "product/memory",
        "product/vcpu",
        "reservation/ReservationARN",
        "reservation/NumberOfReservations",
        "reservation/UnitsPerReservation",
        "reservation/StartTime",
        "reservation/EndTime",
    }

    INGRESS_ALT_COLUMNS = {
        "bill_billing_entity",
        "bill_bill_type",
        "bill_payer_account_id",
        "bill_billing_period_start_date",
        "bill_billing_period_end_date",
        "bill_invoice_id",
        "line_item_line_item_type",
        "line_item_usage_account_id",
        "line_item_usage_start_date",
        "line_item_usage_end_date",
        "line_item_product_code",
        "line_item_usage_type",
        "line_item_operation",
        "line_item_availability_zone",
        "line_item_resource_id",
        "line_item_usage_amount",
        "line_item_normalization_factor",
        "line_item_normalized_usage_amount",
        "line_item_currency_code",
        "line_item_unblended_rate",
        "line_item_unblended_cost",
        "line_item_blended_rate",
        "line_item_blended_cost",
        "savings_plan_savings_plan_effective_cost",
        "line_item_tax_type",
        "pricing_public_on_demand_cost",
        "pricing_public_on_demand_rate",
        "reservation_amortized_upfront_fee_for_billing_period",
        "reservation_amortized_upfront_cost_for_usage",
        "reservation_recurring_fee_for_usage",
        "reservation_unused_quantity",
        "reservation_unused_recurring_fee",
        "pricing_term",
        "pricing_unit",
        "product_sku",
        "product_product_name",
        "product_product_family",
        "product_servicecode",
        "product_region",
        "product_instance_type",
        "product_memory",
        "product_vcpu",
        "reservation_number_of_reservations",
        "reservation_units_per_reservation",
        "reservation_start_time",
        "reservation_end_time",
    }

    COL_TRANSLATION = {
        "bill_billing_entity": "bill/BillingEntity",
        "bill_bill_type": "bill/BillType",
        "bill_payer_account_id": "bill/PayerAccountId",
        "bill_billing_period_start_date": "bill/BillingPeriodStartDate",
        "bill_billing_period_end_date": "bill/BillingPeriodEndDate",
        "bill_invoice_id": "bill/InvoiceId",
        "line_item_line_item_type": "lineItem/LineItemType",
        "line_item_usage_account_id": "lineItem/UsageAccountId",
        "line_item_usage_start_date": "lineItem/UsageStartDate",
        "line_item_usage_end_date": "lineItem/UsageEndDate",
        "line_item_product_code": "lineItem/ProductCode",
        "line_item_usage_type": "lineItem/UsageType",
        "line_item_operation": "lineItem/Operation",
        "line_item_availability_zone": "lineItem/AvailabilityZone",
        "line_item_resource_id": "lineItem/ResourceId",
        "line_item_usage_amount": "lineItem/UsageAmount",
        "line_item_normalization_factor": "lineItem/NormalizationFactor",
        "line_item_normalized_usage_amount": "lineItem/NormalizedUsageAmount",
        "line_item_currency_code": "lineItem/CurrencyCode",
        "line_item_unblended_rate": "lineItem/UnblendedRate",
        "line_item_unblended_cost": "lineItem/UnblendedCost",
        "line_item_blended_rate": "lineItem/BlendedRate",
        "line_item_blended_cost": "lineItem/BlendedCost",
        "savings_plan_savings_plan_effective_cost": "savingsPlan/SavingsPlanEffectiveCost",
        "line_item_tax_type": "lineItem/TaxType",
        "pricing_public_on_demand_cost": "pricing/publicOnDemandCost",
        "pricing_public_on_demand_rate": "pricing/publicOnDemandRate",
        "reservation_amortized_upfront_fee_for_billing_period": "reservation/AmortizedUpfrontFeeForBillingPeriod",
        "reservation_amortized_upfront_cost_for_usage": "reservation/AmortizedUpfrontCostForUsage",
        "reservation_recurring_fee_for_usage": "reservation/RecurringFeeForUsage",
        "reservation_unused_quantity": "reservation/UnusedQuantity",
        "reservation_unused_recurring_fee": "reservation/UnusedRecurringFee",
        "pricing_term": "pricing/term",
        "pricing_unit": "pricing/unit",
        "product_sku": PRODUCT_SKU_COL,
        "product_product_name": "product/ProductName",
        "product_product_family": "product/productFamily",
        "product_servicecode": "product/servicecode",
        "product_region": "product/region",
        "product_instance_type": "product/instanceType",
        "product_memory": "product/memory",
        "product_vcpu": "product/vcpu",
        "reservation_number_of_reservations": "reservation/NumberOfReservations",
        "reservation_units_per_reservation": "reservation/UnitsPerReservation",
        "reservation_start_time": "reservation/StartTime",
        "reservation_end_time": "reservation/EndTime",
    }

    CSV_COLUMN_PREFIX = (
        ALL_RESOURCE_TAG_PREFIX,
        COST_CATEGORY_PREFIX,
        "bill/",
        "lineItem/",
        "pricing/",
        "discount/",
        PRODUCT_SKU_COL,
    )

    def __init__(self, schema):
        self.schema = schema
        self.enabled_tag_keys = set()
        self.enabled_categories = set()

    def check_ingress_required_columns(self, col_names):
        """
        Checks the required columns for ingress.
        """
        if not set(col_names).issuperset(self.INGRESS_REQUIRED_COLUMNS):
            if not set(col_names).issuperset(self.INGRESS_ALT_COLUMNS):
                missing_columns = [x for x in self.INGRESS_ALT_COLUMNS if x not in col_names]
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
        csv_columns = self.INGRESS_REQUIRED_COLUMNS | self.INGRESS_ALT_COLUMNS
        panda_kwargs["usecols"] = [
            col for col in col_names if col in csv_columns or col.startswith(self.CSV_COLUMN_PREFIX)  # AWS specific
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
                "lineitem_lineitemtype",
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
        org_columns = data_frame.columns.unique()
        columns = []
        for col in org_columns:
            if "/" not in col and self.COL_TRANSLATION.get(col):
                data_frame = data_frame.rename(columns={col: self.COL_TRANSLATION[col]})
                columns.append(self.COL_TRANSLATION[col])
        columns = set(TRINO_REQUIRED_COLUMNS).union(data_frame)
        columns = sorted(list(columns))

        tags, unique_tag_keys = handle_user_defined_json_columns(data_frame, columns, self.RESOURCE_TAG_USER_PREFIX)
        self.enabled_tag_keys.update(unique_tag_keys)
        data_frame["resourceTags"] = tags

        cost_categories, aws_category_keys = handle_user_defined_json_columns(
            data_frame, columns, self.COST_CATEGORY_PREFIX
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
            if self.ALL_RESOURCE_TAG_PREFIX in column or self.COST_CATEGORY_PREFIX in column:
                drop_columns.append(column)
        data_frame = data_frame.drop(columns=drop_columns)
        data_frame = data_frame.rename(columns=column_name_map)
        return data_frame, self._generate_daily_data(data_frame)

    def finalize_post_processing(self):
        """
        Uses information gather in the
        """
        create_enabled_keys(self.schema, AWSEnabledTagKeys, self.enabled_tag_keys)
        create_enabled_keys(self.schema, AWSEnabledCategoryKeys, self.enabled_categories)
