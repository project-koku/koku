from uuid import uuid4

from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

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


class ParentTagKeys(models.Model):
    parent = models.OneToOneField("EnabledTagKeys", on_delete=models.CASCADE, primary_key=True, null=False)


class ChildTagKeys(models.Model):
    class Meta:
        unique_together = ("parent", "child")

    child = models.OneToOneField("EnabledTagKeys", on_delete=models.CASCADE, null=False, primary_key=True)
    parent = models.OneToOneField("ParentTagKeys", on_delete=models.CASCADE, null=False)


@receiver(post_delete, sender=ChildTagKeys)
def delete_childless_parent(sender, instance, **kwargs):
    # Delete the parent if it has no associated children
    parent_tag = instance.parent
    if parent_tag and not ChildTagKeys.objects.filter(parent=parent_tag).exists():
        parent_tag.delete()
