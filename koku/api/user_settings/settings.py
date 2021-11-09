#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
# turn off black formatting
# fmt: off
"""List of cost_types."""
COST_TYPES = [
    {
        "code": "unblended_cost",
        "name": "Unblended",
        "description": "Usage cost on the day you are charged",
    },
    {
        "code": "savingsplan_effective_cost",
        "name": "Amortized",
        "description": "recurring and/or upfront costs are distributed evenly across the month",
    },
    {
        "code": "blended_cost",
        "name": "Blended",
        "description": "Using a blended rate to calculate cost usage",
    },
]
# fmt: on
