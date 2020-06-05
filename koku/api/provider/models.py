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
"""Models for provider management."""
import logging
from uuid import uuid4

from django.conf import settings
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.db import transaction
from django.db.models.constraints import CheckConstraint

LOG = logging.getLogger(__name__)


class ProviderAuthentication(models.Model):
    """A Koku Provider Authentication.

    Used for accessing cost providers data like AWS Accounts.
    """

    uuid = models.UUIDField(default=uuid4, editable=False, unique=True, null=False)

    # XXX: This field is DEPRECATED
    # XXX: the credentials field should be used instead.
    # Ex: AWS ARN for cross-account role access
    provider_resource_name = models.TextField(null=True, unique=True)

    credentials = JSONField(null=True, default=dict)

    class Meta:
        """Meta class."""

        # The goal is to ensure that exactly one field is not null.
        constraints = [
            # NOT (provider_resource_name IS NULL AND credentials IS NULL)
            CheckConstraint(
                check=~models.Q(models.Q(provider_resource_name=None) & models.Q(credentials={})),
                name="credentials_and_resource_name_both_null",
            )
        ]


class ProviderBillingSource(models.Model):
    """A Koku Provider Billing Source.

    Used for accessing cost providers billing sourece like AWS Account S3.
    """

    uuid = models.UUIDField(default=uuid4, editable=False, unique=True, null=False)

    # XXX: This field is DEPRECATED
    # XXX: the data_source field should be used instead.
    bucket = models.CharField(max_length=63, null=True)

    data_source = JSONField(null=True, default=dict)

    class Meta:
        """Meta class."""

        # The goal is to ensure that exactly one field is not null.
        constraints = [
            # NOT (bucket IS NULL AND data_source IS NULL)
            CheckConstraint(
                check=~models.Q(models.Q(bucket=None) & models.Q(data_source={})),
                name="bucket_and_data_source_both_null",
            )
        ]


class Provider(models.Model):
    """A Koku Provider.

    Used for modeling cost providers like AWS Accounts.
    """

    class Meta:
        """Meta for Provider."""

        ordering = ["name"]
        unique_together = ("authentication", "billing_source", "customer")

    PROVIDER_AWS = "AWS"
    PROVIDER_OCP = "OCP"
    PROVIDER_AZURE = "Azure"
    PROVIDER_GCP = "GCP"
    # Local Providers are for local development and testing
    PROVIDER_AWS_LOCAL = "AWS-local"
    PROVIDER_AZURE_LOCAL = "Azure-local"
    PROVIDER_GCP_LOCAL = "GCP-local"
    # The following constants are not provider types
    OCP_ALL = "OCP_All"
    OCP_AWS = "OCP_AWS"
    OCP_AZURE = "OCP_Azure"

    PROVIDER_CASE_MAPPING = {
        "aws": PROVIDER_AWS,
        "ocp": PROVIDER_OCP,
        "azure": PROVIDER_AZURE,
        "gcp": PROVIDER_GCP,
        "aws-local": PROVIDER_AWS_LOCAL,
        "azure-local": PROVIDER_AZURE_LOCAL,
        "gcp-local": PROVIDER_GCP_LOCAL,
        "ocp-aws": OCP_AWS,
        "ocp-azure": OCP_AZURE,
    }

    PROVIDER_CHOICES = (
        (PROVIDER_AWS, PROVIDER_AWS),
        (PROVIDER_OCP, PROVIDER_OCP),
        (PROVIDER_AZURE, PROVIDER_AZURE),
        (PROVIDER_GCP, PROVIDER_GCP),
        (PROVIDER_AWS_LOCAL, PROVIDER_AWS_LOCAL),
        (PROVIDER_AZURE_LOCAL, PROVIDER_AZURE_LOCAL),
        (PROVIDER_GCP_LOCAL, PROVIDER_GCP_LOCAL),
    )
    CLOUD_PROVIDER_CHOICES = (
        (PROVIDER_AWS, PROVIDER_AWS),
        (PROVIDER_AZURE, PROVIDER_AZURE),
        (PROVIDER_GCP, PROVIDER_GCP),
        (PROVIDER_AWS_LOCAL, PROVIDER_AWS_LOCAL),
        (PROVIDER_AZURE_LOCAL, PROVIDER_AZURE_LOCAL),
        (PROVIDER_GCP_LOCAL, PROVIDER_GCP_LOCAL),
    )

    # These lists are intended for use for provider type checking
    # throughout the codebase
    PROVIDER_LIST = [choice[0] for choice in PROVIDER_CHOICES]
    CLOUD_PROVIDER_LIST = [choice[0] for choice in CLOUD_PROVIDER_CHOICES]

    uuid = models.UUIDField(default=uuid4, primary_key=True)
    name = models.CharField(max_length=256, null=False)
    type = models.CharField(max_length=50, null=False, choices=PROVIDER_CHOICES, default=PROVIDER_AWS)
    authentication = models.ForeignKey("ProviderAuthentication", null=True, on_delete=models.DO_NOTHING)
    billing_source = models.ForeignKey("ProviderBillingSource", null=True, on_delete=models.DO_NOTHING, blank=True)
    customer = models.ForeignKey("Customer", null=True, on_delete=models.PROTECT)
    created_by = models.ForeignKey("User", null=True, on_delete=models.SET_NULL)
    setup_complete = models.BooleanField(default=False)

    created_timestamp = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    active = models.BooleanField(default=True)

    # This field applies to OpenShift providers and identifies
    # which (if any) cloud provider the cluster is on
    infrastructure = models.ForeignKey("ProviderInfrastructureMap", null=True, on_delete=models.SET_NULL)

    def save(self, *args, **kwargs):
        """Save instance and start data ingest task for active Provider."""

        should_ingest = False
        # These values determine if a Provider is new
        if self.created_timestamp and not self.setup_complete:
            should_ingest = True

        try:
            provider = Provider.objects.get(uuid=self.uuid)
        except Provider.DoesNotExist:
            pass
        else:
            # These values determine if Provider credentials have been updated:
            if provider.authentication != self.authentication or provider.billing_source != self.billing_source:
                should_ingest = True

        # Commit the new/updated Provider to the DB
        super().save(*args, **kwargs)

        if settings.AUTO_DATA_INGEST and should_ingest and self.active:
            # Local import of task function to avoid potential import cycle.
            from masu.celery.tasks import check_report_updates

            LOG.info(f"Starting data ingest task for Provider {self.uuid}")
            # Start check_report_updates task after Provider has been committed.
            transaction.on_commit(lambda: check_report_updates.delay(provider_uuid=self.uuid))


class Sources(models.Model):
    """Platform-Sources table.

    Used for managing Platform-Sources.
    """

    class Meta:
        """Meta for Sources."""

        db_table = "api_sources"
        ordering = ["name"]

    # Backend Platform-Services data.
    # Source ID is unique identifier
    source_id = models.IntegerField(primary_key=True)

    # Source UID
    source_uuid = models.UUIDField(unique=True, null=True)

    # Source name.
    name = models.CharField(max_length=256, null=True)

    # Red Hat identity header.  Passed along to Koku API for entitlement and rbac reasons.
    auth_header = models.TextField(null=True)

    # Kafka message offset for Platform-Sources kafka stream
    offset = models.IntegerField(null=False)

    # Endpoint ID.  Identifier to connect source to authentication.
    endpoint_id = models.IntegerField(null=True)

    # Koku Specific data.
    # Customer Account ID
    account_id = models.CharField(max_length=150, null=True)

    # Provider type (i.e. AWS, OCP, AZURE)
    source_type = models.CharField(max_length=50, null=False)

    # Provider authentication (AWS roleARN, OCP Sources UID, etc.)
    authentication = JSONField(null=False, default=dict)

    # Provider billing source (AWS S3 bucket)
    billing_source = JSONField(null=True, default=dict)

    # Unique identifier for koku Provider
    koku_uuid = models.CharField(max_length=512, null=True, unique=True)

    # When source has been deleted on Platform-Sources this is True indicating it hasn't been
    # removed on the Koku side yet.  Entry is removed entirely once Koku-Provider was successfully
    # removed.
    pending_delete = models.BooleanField(default=False)

    # When a source is being updated by either Platform-Sources or from API (auth, billing source)
    # this flag will indicate that the update needs to be picked up by the Koku-Provider synchronization
    # handler.
    pending_update = models.BooleanField(default=False)

    # When a source delete occurs before a source create.  Messages can be out of order when arriving
    # on different kafka partitions.
    out_of_order_delete = models.BooleanField(default=False)

    # Availability status
    status = JSONField(null=True, default=dict)

    def __str__(self):
        """Get the string representation."""
        return (
            f"Source ID: {self.source_id}\nName: {self.name}\nSource UUID: {self.source_uuid}\n"
            f"Source Type: {self.source_type}\nAuthentication: {self.authentication}\n"
            f"Billing Source: {self.billing_source}\nKoku UUID: {self.koku_uuid}\n"
            f"Pending Delete: {self.pending_delete}\nPending Update: {self.pending_update}\n"
        )


class ProviderStatus(models.Model):
    """Koku provider status.

    Used for tracking provider status.

    """

    # Provider states used to signal whether the Provider is suitable for
    # attempting to download and process reports.
    #
    # These states are duplicated in masu.database.provider_db_accessor
    #
    STATES = ((0, "New"), (1, "Ready"), (33, "Warning"), (98, "Disabled: Error"), (99, "Disabled: Admin"))

    provider = models.ForeignKey("Provider", on_delete=models.CASCADE)
    status = models.IntegerField(null=False, choices=STATES, default=0)
    last_message = models.CharField(max_length=256, null=False)
    timestamp = models.DateTimeField()
    retries = models.IntegerField(null=False, default=0)


class ProviderInfrastructureMap(models.Model):
    """A lookup table for OpenShift providers.

    Used to determine which underlying instrastructure and
    associated provider the cluster is installed on.
    """

    infrastructure_type = models.CharField(max_length=50, choices=Provider.CLOUD_PROVIDER_CHOICES, blank=False)
    infrastructure_provider = models.ForeignKey("Provider", on_delete=models.CASCADE)
