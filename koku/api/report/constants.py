#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Constants file."""

TAG_PREFIX = "tag:"
AND_PREFIX = "and:"
OR_PREFIX = "or:"
EXACT_PREFIX = "exact:"
AWS_CATEGORY_PREFIX = "aws_category:"
URL_ENCODED_SAFE = "[]:"
AWS_MARKUP_COST = {
    "blended_cost": "markup_cost_blended",
    "savingsplan_effective_cost": "markup_cost_savingsplan",
    "calculated_amortized_cost": "markup_cost_amortized",
}
AWS_COST_TYPE_CHOICES = (
    ("blended_cost", "blended_cost"),
    ("unblended_cost", "unblended_cost"),
    ("calculated_amortized_cost", "calculated_amortized_cost"),
    # savingsplan_effective_cost is for backwards compatibility.
    # Use calculated_amortized_cost for the correct amortized cost value.
    ("savingsplan_effective_cost", "savingsplan_effective_cost"),
)

TIME_SCOPE_VALUES_MONTHLY = ("-1", "-2", "-3")
TIME_SCOPE_VALUES_DAILY = ("-10", "-30", "-90")
TIME_SCOPE_UNITS_MONTHLY = "month"
TIME_SCOPE_UNITS_DAILY = "day"
RESOLUTION_MONTHLY = "monthly"
RESOLUTION_DAILY = "daily"
