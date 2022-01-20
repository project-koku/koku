#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for provider management."""
import logging
from uuid import uuid4

from django.conf import settings
from django.core.validators import MaxLengthValidator
from django.db import models
from django.db import router
from django.db import transaction
from django.db.models import JSONField
from django.db.models.signals import post_delete
from tenant_schemas.utils import schema_context

from api.model_utils import RunTextFieldValidators
from koku.database import cascade_delete

LOG = logging.getLogger(__name__)


class ProviderAuthentication(models.Model):
    """A Koku Provider Authentication.

    Used for accessing cost providers data like AWS Accounts.
    """

    uuid = models.UUIDField(default=uuid4, editable=False, unique=True, null=False)

    credentials = JSONField(null=False, default=dict)


class ProviderBillingSource(models.Model):
    """A Koku Provider Billing Source.

    Used for accessing cost providers billing sourece like AWS Account S3.
    """

    uuid = models.UUIDField(default=uuid4, editable=False, unique=True, null=False)

    data_source = JSONField(null=False, default=dict)


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
    PROVIDER_IBM = "IBM"
    # Local Providers are for local development and testing
    PROVIDER_AWS_LOCAL = "AWS-local"
    PROVIDER_AZURE_LOCAL = "Azure-local"
    PROVIDER_GCP_LOCAL = "GCP-local"
    PROVIDER_IBM_LOCAL = "IBM-local"
    # The following constants are not provider types
    OCP_ALL = "OCP_All"
    OCP_AWS = "OCP_AWS"
    OCP_AZURE = "OCP_Azure"

    PROVIDER_CASE_MAPPING = {
        "aws": PROVIDER_AWS,
        "ocp": PROVIDER_OCP,
        "azure": PROVIDER_AZURE,
        "gcp": PROVIDER_GCP,
        "ibm": PROVIDER_IBM,
        "aws-local": PROVIDER_AWS_LOCAL,
        "azure-local": PROVIDER_AZURE_LOCAL,
        "gcp-local": PROVIDER_GCP_LOCAL,
        "ibm-local": PROVIDER_IBM_LOCAL,
        "ocp-aws": OCP_AWS,
        "ocp-azure": OCP_AZURE,
    }

    PROVIDER_CHOICES = (
        (PROVIDER_AWS, PROVIDER_AWS),
        (PROVIDER_OCP, PROVIDER_OCP),
        (PROVIDER_AZURE, PROVIDER_AZURE),
        (PROVIDER_GCP, PROVIDER_GCP),
        (PROVIDER_IBM, PROVIDER_IBM),
        (PROVIDER_AWS_LOCAL, PROVIDER_AWS_LOCAL),
        (PROVIDER_AZURE_LOCAL, PROVIDER_AZURE_LOCAL),
        (PROVIDER_GCP_LOCAL, PROVIDER_GCP_LOCAL),
        (PROVIDER_IBM_LOCAL, PROVIDER_IBM_LOCAL),
    )
    CLOUD_PROVIDER_CHOICES = (
        (PROVIDER_AWS, PROVIDER_AWS),
        (PROVIDER_AZURE, PROVIDER_AZURE),
        (PROVIDER_GCP, PROVIDER_GCP),
        (PROVIDER_IBM, PROVIDER_IBM),
        (PROVIDER_AWS_LOCAL, PROVIDER_AWS_LOCAL),
        (PROVIDER_AZURE_LOCAL, PROVIDER_AZURE_LOCAL),
        (PROVIDER_GCP_LOCAL, PROVIDER_GCP_LOCAL),
        (PROVIDER_IBM_LOCAL, PROVIDER_IBM_LOCAL),
    )

    # These lists are intended for use for provider type checking
    # throughout the codebase
    PROVIDER_LIST = [choice[0] for choice in PROVIDER_CHOICES]
    CLOUD_PROVIDER_LIST = [choice[0] for choice in CLOUD_PROVIDER_CHOICES]
    OPENSHIFT_ON_CLOUD_PROVIDER_LIST = [
        PROVIDER_AWS,
        PROVIDER_AWS_LOCAL,
        PROVIDER_AZURE,
        PROVIDER_AZURE_LOCAL,
        PROVIDER_GCP,
        PROVIDER_GCP_LOCAL,
    ]

    uuid = models.UUIDField(default=uuid4, primary_key=True)
    name = models.CharField(max_length=256, null=False)
    type = models.CharField(max_length=50, null=False, choices=PROVIDER_CHOICES, default=PROVIDER_AWS)
    authentication = models.ForeignKey("ProviderAuthentication", null=True, on_delete=models.DO_NOTHING)
    billing_source = models.ForeignKey("ProviderBillingSource", null=True, on_delete=models.DO_NOTHING, blank=True)
    customer = models.ForeignKey("Customer", null=True, on_delete=models.PROTECT)
    created_by = models.ForeignKey("User", null=True, on_delete=models.SET_NULL)
    setup_complete = models.BooleanField(default=False)

    created_timestamp = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    # We update the record on the provider when we update data.
    # This helps capture events like the updates following a cost model
    # CRUD operation that triggers cost model cost summarization,
    # but not on a specific manifest, so no manifest timestamp is updated
    data_updated_timestamp = models.DateTimeField(null=True)

    active = models.BooleanField(default=True)
    paused = models.BooleanField(default=False)

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
            else:
                should_ingest = False

        # Commit the new/updated Provider to the DB
        super().save(*args, **kwargs)

        if settings.AUTO_DATA_INGEST and should_ingest and self.active:
            # Local import of task function to avoid potential import cycle.
            from masu.celery.tasks import check_report_updates

            LOG.info(f"Starting data ingest task for Provider {self.uuid}")
            # Start check_report_updates task after Provider has been committed.
            transaction.on_commit(lambda: check_report_updates.delay(provider_uuid=self.uuid))

    def delete(self, *args, **kwargs):
        if self.customer:
            using = router.db_for_write(self.__class__, isinstance=self)
            with schema_context(self.customer.schema_name):
                LOG.info(f"PROVIDER {self.name} ({self.pk}) CASCADE DELETE -- SCHEMA {self.customer.schema_name}")
                cascade_delete(self.__class__, self.__class__.objects.filter(pk=self.pk))
                post_delete.send(sender=self.__class__, instance=self, using=using)
        else:
            LOG.warning("Cannot customer link cannot be found! Using ORM delete!")
            super().delete()


class Sources(RunTextFieldValidators, models.Model):
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
    name = models.TextField(max_length=256, null=True, validators=[MaxLengthValidator(256)])

    # Red Hat identity header.  Passed along to Koku API for entitlement and rbac reasons.
    auth_header = models.TextField(null=True)

    # Kafka message offset for Platform-Sources kafka stream
    offset = models.IntegerField(null=False)

    # Koku Specific data.
    # Customer Account ID
    account_id = models.TextField(null=True)

    # Provider type (i.e. AWS, OCP, AZURE)
    source_type = models.TextField(null=False)

    # Provider authentication (AWS roleARN, OCP Sources UID, etc.)
    authentication = JSONField(null=False, default=dict)

    # Provider billing source (AWS S3 bucket)
    billing_source = JSONField(null=True, default=dict)

    # Unique identifier for koku Provider
    koku_uuid = models.TextField(null=True, unique=True)

    # This field indicates if the source is paused.
    paused = models.BooleanField(default=False)

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


class ProviderInfrastructureMap(models.Model):
    """A lookup table for OpenShift providers.

    Used to determine which underlying instrastructure and
    associated provider the cluster is installed on.
    """

    infrastructure_type = models.CharField(max_length=50, choices=Provider.CLOUD_PROVIDER_CHOICES, blank=False)
    infrastructure_provider = models.ForeignKey("Provider", on_delete=models.CASCADE)
