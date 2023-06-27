#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from koku.settings import KOKU_DEFAULT_COST_TYPE
from koku.settings import KOKU_DEFAULT_CURRENCY

"""List of cost_types."""
COST_TYPES = [
    {
        "code": "unblended_cost",
        "name": "Unblended",
        "description": "Usage cost on the day you are charged",
    },
    {
        "code": "calculated_amortized_cost",
        "name": "Amortized",
        "description": "Recurring and/or upfront costs are distributed evenly across the month",
    },
    {
        "code": "blended_cost",
        "name": "Blended",
        "description": "Using a blended rate to calculate cost usage",
    },
]
VALID_COST_TYPES = [cost_type["code"] for cost_type in COST_TYPES]
COST_TYPE_CHOICES = tuple((currency, currency) for currency in VALID_COST_TYPES)

"""Default users settings"""
# fmt: off
USER_SETTINGS = {
    "settings":
        {
            "currency": KOKU_DEFAULT_CURRENCY,
            "cost_type": KOKU_DEFAULT_COST_TYPE,
        }
}
# fmt: on
