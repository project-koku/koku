#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common utilities and helpers for Currency."""
import json
import os


CURRENCY_FILE_NAME = f"{os.path.dirname(os.path.realpath(__file__))}/specs/currencies.json"


def load_currencies_from_file(file_path=CURRENCY_FILE_NAME):
    with open(file_path) as api_file:
        data = json.load(api_file)
        return data
