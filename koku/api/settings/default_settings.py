#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Set of default settings for the user_settings table jsonfield"""
from koku.settings import KOKU_DEFAULT_COST_TYPE
from koku.settings import KOKU_DEFAULT_CURRENCY

DEFAULT_USER_SETTINGS = {"currency": KOKU_DEFAULT_CURRENCY, "cost_type": KOKU_DEFAULT_COST_TYPE}
