#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Constants file."""

TAG_PREFIX = "tag:"
AND_TAG_PREFIX = "and:tag:"
OR_TAG_PREFIX = "or:tag:"
EXACT_TAG_PREFIX = "exact:tag:"
AWS_CATEGORY_PREFIX = "aws_category:"
AND_AWS_CATEGORY_PREFIX = "and:aws_category:"
OR_AWS_CATEGORY_PREFIX = "or:aws_category:"
EXACT_AWS_CATEGORY_PREFIX = "exact:aws_category:"
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
# Defines the set of query parameters that are eligible for the special
# OR-logic that combines a partial match
# (e.g., `filter[node]=...`) with an exact match (`filter[exact:node]=...`).
FILTERS_WITH_EXACT_SUPPORT = {
    "account",
    "service",
    "az",
    "region",
    "product_family",
    "instance_type",
    "operating_system",
    "instance",
    "subscription_guid",
    "service_name",
    "resource_location",
    "gcp_project",
    "category",
    "project",
    "cluster",
    "persistentvolumeclaim",
    "storageclass",
    "pod",
    "node",
    "vm_name",
}
