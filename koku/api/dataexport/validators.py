"""Validators for user-initiated data exports."""
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError

from api.dataexport.models import DataExportRequest


class DataExportRequestValidator:
    """Validator that ensures date fields are appropriately defined for a new request."""

    requires_context = True

    def pending_instance_exists(self, start_date, end_date):
        """Check for a pending or processing instance that matches the requested dates."""
        if self.instance is not None:
            # This is an update and does not need to check for existence.
            return
        queryset = self.queryset.filter(
            status__in=(DataExportRequest.PENDING, DataExportRequest.PROCESSING),
            start_date=start_date,
            end_date=end_date,
        )
        return queryset.exists()

    def __call__(self, attrs, serializer_field):
        """Enforce validation of all relevant fields."""

        # Set extra data from the serializer to do extra lookup validation.
        self.queryset = serializer_field.context["view"].get_queryset()
        self.instance = getattr(serializer_field, "instance", None)

        start_date = attrs["start_date"]
        end_date = attrs["end_date"]
        if end_date < start_date:
            bad_items = {
                "start_date": _('"start_date" must be older than "end_date".'),
                "end_date": _('"end_date" must not be older than "start_date".'),
            }
            raise ValidationError(bad_items, code="bad_request")
        if self.pending_instance_exists(start_date, end_date):
            exists_message = _(
                "A pending or processing data export already exists with the given " '"start_date" and "end_date".'
            )
            raise ValidationError(exists_message, code="bad_request")
