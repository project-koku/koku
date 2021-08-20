#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""PostgreSQL DB functions for use by Django ORM."""
from django.db.models.aggregates import Func


class JSONBObjectKeys(Func):
    """Helper to get json keys."""

    function = "jsonb_object_keys"
    template = "%(function)s(%(expressions)s)"
    arity = 1
