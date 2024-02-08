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
    key = models.CharField(max_length=512)
    enabled = models.BooleanField(default=True)
    provider_type = models.CharField(max_length=50, null=False, choices=Provider.PROVIDER_CHOICES)


class TagMapping(models.Model):
    """This model encompasses a hierarchical mapping of parent-to-child relationships,
    offering a mechanism for customers to substitute the child's key with the parent's
    key within the daily summary table.
    """

    class Meta:
        """Meta for TagMapping."""

        db_table = "reporting_tagmapping"
        unique_together = ("parent", "child")

    parent = models.ForeignKey("EnabledTagKeys", on_delete=models.CASCADE, related_name="parent")
    child = models.OneToOneField("EnabledTagKeys", on_delete=models.CASCADE, related_name="child")
