#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Django model mixins and utilities."""


class RunTextFieldValidators:
    """
    Mixin to run all field validators on a save method call
    This mixin should appear BEFORE Model.
    """

    def save(self, *args, **kwargs):
        """
        For all fields, run any default and specified validators before calling save
        """
        for f in (
            c for c in self._meta.get_fields() if hasattr(self, c.name) and c.get_internal_type() == "TextField"
        ):
            val = getattr(self, f.name)
            if val is not None:
                val = str(val)
            f.run_validators(val)

        super().save(*args, **kwargs)
