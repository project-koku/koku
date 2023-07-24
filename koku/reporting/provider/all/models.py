from uuid import uuid4

from django.db import models

from api.provider.models import Provider


class EnabledTagKeys(models.Model):
    """A collection of the current enabled tag keys."""

    class Meta:
        """Meta for EnabledTagKeys."""

        indexes = [
            models.Index(fields=["key", "enabled"], name="tag_enabled_key_index"),
            models.Index(fields=["provider_type"], name="tag_provider_type_index"),
        ]
        db_table = "reporting_enabledtagkeys"
        unique_together = ("key", "provider_type")

    uuid = models.UUIDField(default=uuid4, editable=False, unique=True, null=False, primary_key=True)
    key = models.CharField(max_length=253)
    enabled = models.BooleanField(default=True)
    provider_type = models.CharField(max_length=50, null=False, choices=Provider.PROVIDER_CHOICES)
