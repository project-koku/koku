"""Validators for user-initiated data exports."""

from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError


class DataExportRequestValidator:
    """Validator that ensures date fields are appropriately ordered."""

    def __call__(self, attrs):
        """Enforce validation of all relevant fields."""
        start_date = attrs['start_date']
        end_date = attrs['end_date']
        if end_date < start_date:
            bad_items = {
                'start_date': _('"start_date" must be older than "end_date".'),
                'end_date': _('"end_date" must not be older than "start_date".'),
            }
            raise ValidationError(bad_items, code='bad_request')
