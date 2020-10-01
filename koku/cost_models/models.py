#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Models for cost models."""
import logging
from uuid import uuid4

from django.contrib.postgres.fields import ArrayField
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import JSONField

from api.provider.models import Provider


LOG = logging.getLogger(__name__)


class CostModel(models.Model):
    """A collection of rates used to calculate cost against resource usage data."""

    class Meta:
        """Meta for CostModel."""

        db_table = "cost_model"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"], name="name_idx"),
            models.Index(fields=["source_type"], name="source_type_idx"),
            models.Index(fields=["updated_timestamp"], name="updated_timestamp_idx"),
        ]

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    name = models.TextField()

    description = models.TextField()

    source_type = models.CharField(max_length=50, null=False, choices=Provider.PROVIDER_CHOICES)

    created_timestamp = models.DateTimeField(auto_now_add=True)

    updated_timestamp = models.DateTimeField(auto_now=True)

    rates = JSONField(default=dict)

    markup = JSONField(encoder=DjangoJSONEncoder, default=dict)


class CostModelAudit(models.Model):
    """A collection of rates used to calculate cost against resource usage data."""

    class Meta:
        """Meta for CostModel."""

        db_table = "cost_model_audit"

    operation = models.CharField(max_length=16)

    audit_timestamp = models.DateTimeField()

    provider_uuids = ArrayField(models.UUIDField(), null=True)

    uuid = models.UUIDField()

    name = models.TextField()

    description = models.TextField()

    source_type = models.CharField(max_length=50, null=False, choices=Provider.PROVIDER_CHOICES)

    created_timestamp = models.DateTimeField()

    updated_timestamp = models.DateTimeField()

    rates = JSONField(default=dict)

    markup = JSONField(encoder=DjangoJSONEncoder, default=dict)


class CostModelMap(models.Model):
    """Map for provider and rate objects."""

    provider_uuid = models.UUIDField(editable=False, unique=False, null=False)

    cost_model = models.ForeignKey("CostModel", null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        """Meta for CostModelMap."""

        ordering = ["-id"]
        unique_together = ("provider_uuid", "cost_model")
        db_table = "cost_model_map"
