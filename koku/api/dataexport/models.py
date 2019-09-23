"""Models for user-initiated data exports."""

from uuid import uuid4

from django.db import models

from api.iam.models import User


class DataExportRequest(models.Model):
    """A user's request for a data export."""

    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETE = 'complete'
    ERROR = 'error'
    STATUS_CHOICES = ((PENDING, 'Pending'), (PROCESSING, 'Processing'), (COMPLETE, 'Complete'), (ERROR, 'Error'))

    uuid = models.UUIDField(default=uuid4, editable=False, unique=True, null=False)
    created_by = models.ForeignKey('User', null=False, on_delete=models.CASCADE)
    created_timestamp = models.DateTimeField(auto_now_add=True)
    updated_timestamp = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=PENDING)
    start_date = models.DateField(null=False)
    end_date = models.DateField(null=False)
    bucket_name = models.CharField(max_length=63)

    class Meta:
        ordering = ('created_timestamp',)

    def __str__(self):
        """Get the string representation."""
        return self.__repr__()

    def __repr__(self):
        """Get an unambiguous string representation."""
        start_date = (
            repr(self.start_date.isoformat()) if self.start_date is not None else None
        )
        end_date = (
            repr(self.end_date.isoformat()) if self.end_date is not None else None
        )
        try:
            created_by = self.created_by.id
        except User.DoesNotExist:
            created_by = None
        created_timestamp = (
            repr(self.created_timestamp.isoformat())
            if self.created_timestamp is not None
            else None
        )
        updated_timestamp = (
            repr(self.updated_timestamp.isoformat())
            if self.updated_timestamp is not None
            else None
        )
        return (
            f'{self.__class__.__name__}: uuid: {self.uuid}, '
            f'status: {self.status}, start_date: {start_date}, end_date: {end_date}, '
            f'bucket_name: {self.bucket_name}, created_by: {created_by}, '
            f'created_timestamp: {created_timestamp}, updated_timestamp: {updated_timestamp}'
        )
