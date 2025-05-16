#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for provider management."""
import logging
import math
from datetime import datetime
from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.core.validators import MaxLengthValidator
from django.db import connection
from django.db import models
from django.db import router
from django.db import transaction
from django.db.models import JSONField
from django.db.models.query import QuerySet
from django.db.models.signals import post_delete
from django.utils import timezone
from django_tenants.utils import schema_context

from api.model_utils import RunTextFieldValidators
from koku.database import get_model

LOG = logging.getLogger(__name__)


def check_provider_setup_complete(provider_uuid):
    """Return setup complete or None if Provider does not exist."""
    if p := Provider.objects.filter(uuid=provider_uuid).first():
        return p.setup_complete


class ProviderAuthentication(models.Model):
    """A Koku Provider Authentication.

    Used for accessing cost providers data like AWS Accounts.
    """

    uuid = models.UUIDField(default=uuid4, editable=False, unique=True, null=False)

    credentials = JSONField(null=False, default=dict)


class ProviderBillingSource(models.Model):
    """A Koku Provider Billing Source.

    Used for accessing cost providers billing source like AWS Account S3.
    """

    uuid = models.UUIDField(default=uuid4, editable=False, unique=True, null=False)

    data_source = JSONField(null=False, default=dict)


class ProviderObjectsManager(models.Manager):
    """Default manager for Provider model."""

    def get_queryset(self) -> QuerySet:
        """
        Override the default queryset to select the authentication, billing_source, and customer fields.

        This override gives us access to these other fields without needing extra db queries. This make
        the `account` property of the Provider table a single db query instead of one for each foreign key
        lookup. This class should be used as a base class for any new managers created for the Provider model.
        """
        return super().get_queryset().select_related("authentication", "billing_source", "customer")

    def get_accounts(self):
        """Return a list of all accounts."""
        return [p.account for p in self.all()]


class ProviderObjectsPollingManager(ProviderObjectsManager):
    """
    Manager for pollable Providers.

    Pollable Providers are all Providers that are not OCP.
    """

    def get_queryset(self):
        """Return a Queryset of non-OCP and active and non-paused Providers."""
        return super().get_queryset().filter(active=True, paused=False).exclude(type=Provider.PROVIDER_OCP)

    def get_polling_batch(self, filters=None):
        """Return a Queryset of pollable Providers that have not polled in the last 24 hours."""
        polling_delta = datetime.now(tz=settings.UTC) - timedelta(seconds=settings.POLLING_TIMER)
        if not filters:
            filters = {}
        # Dynamically set batch limit (divide count by 21 (default) hours so we always trigger a few extra + round up)
        batch_limit = math.ceil(len(self.filter(**filters)) / settings.POLLING_COUNT)
        if batch_limit <= 1:
            # If we have less than 21 providers we should collect them all
            return self.filter(**filters).exclude(polling_timestamp__gt=polling_delta).order_by("polling_timestamp")
        return (
            self.filter(**filters)
            .exclude(polling_timestamp__gt=polling_delta)
            .order_by("polling_timestamp")[:batch_limit]
        )


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
    OCP_GCP = "OCP_GCP"

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
    MANAGED_OPENSHIFT_ON_CLOUD_PROVIDER_LIST = [
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
    polling_timestamp = models.DateTimeField(blank=True, null=True, default=None)

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
    additional_context = JSONField(null=True, default=dict)
    test_migration = JSONField(null=True, default=dict)

    objects = ProviderObjectsManager()
    polling_objects = ProviderObjectsPollingManager()

    @property
    def account(self) -> dict:
        """Return account information in dictionary."""
        return {
            "customer_name": getattr(self.customer, "schema_name", None),
            "credentials": getattr(self.authentication, "credentials", None),
            "data_source": getattr(self.billing_source, "data_source", None),
            "provider_type": self.type,
            "schema_name": getattr(self.customer, "schema_name", None),
            "account_id": getattr(self.customer, "account_id", None),
            "org_id": getattr(self.customer, "org_id", None),
            "provider_uuid": self.uuid,
        }

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
            if provider.setup_complete != self.setup_complete:
                should_ingest = False

        # Commit the new/updated Provider to the DB
        super().save(*args, **kwargs)

        if settings.AUTO_DATA_INGEST and should_ingest and self.active:
            if self.type == Provider.PROVIDER_OCP:
                # OCP Providers are not pollable, so shouldn't go thru check_report_updates
                return
            # Local import of task function to avoid potential import cycle.
            from masu.celery.tasks import check_report_updates

            QUEUE = None
            if self.customer.schema_name == settings.QE_SCHEMA:
                QUEUE = "priority"
                LOG.info("Setting queue to priority for QE testing")

            LOG.info(f"Starting data ingest task for Provider {self.uuid}")
            # Start check_report_updates task after Provider has been committed.
            transaction.on_commit(
                lambda: check_report_updates.s(provider_uuid=self.uuid, queue_name=QUEUE)
                .set(queue="priority")
                .apply_async()
            )

    def set_additional_context(self, context):
        """Set the `additional_context` field to the provided context."""
        self.additional_context = context
        self.save(update_fields=["additional_context"])

    def set_data_updated_timestamp(self):
        """Set the data updated timestamp to the current time."""
        self.data_updated_timestamp = timezone.now()
        self.save(update_fields=["data_updated_timestamp"])

    def set_infrastructure(self, infra):
        """Set the infrastructure."""
        self.infrastructure = infra
        self.save(update_fields=["infrastructure"])

    def set_setup_complete(self):
        """Set setup_complete to True."""
        self.setup_complete = True
        self.save(update_fields=["setup_complete"])

    def delete(self, *args, **kwargs):
        if self.customer:
            using = router.db_for_write(self.__class__, isinstance=self)
            with schema_context(self.customer.schema_name):
                LOG.info(f"PROVIDER {self.name} ({self.pk}) CASCADE DELETE -- SCHEMA {self.customer.schema_name}")
                _type = self.type.lower()
                self._normalized_type = _type.removesuffix("-local")
                self._cascade_delete()
                LOG.info(f"PROVIDER {self.name} ({self.pk}) CASCADE DELETE COMPLETE")
                LOG.info(f"PROVIDER {self.name} ({self.pk}) DELETING FROM {self._meta.db_table}")
                self._delete_from_target(
                    {"table_schema": "public", "table_name": self._meta.db_table, "column_name": "uuid"},
                    target_values=[self.pk],
                )
                LOG.info(f"PROVIDER {self.name} ({self.pk}) DELETING FROM {self._meta.db_table} COMPLETE")
                post_delete.send(sender=self.__class__, instance=self, using=using)
        else:
            LOG.warning("Customer link cannot be found! Using ORM delete!")
            super().delete()

    def _get_sub_target_values(self, target_info, target_values):
        sub_target = get_model(target_info["table_name"])
        filters = {f"{target_info['column_name']}__in": target_values}
        # This is potentially dnagerous if the sub-target is a partitioned table
        # Care must be taken when calling this method
        sub_target_pk = [f.name for f in sub_target._meta.fields if f.primary_key][0]
        return [r[sub_target_pk] for r in sub_target.objects.filter(**filters).values(sub_target_pk)]

    def _cascade_delete(self, target_table=None, target_values=None, public_schema="public", seen=None):
        if seen is None:
            seen = {"public", "api_providerinfrastructuremap", self.pk}
        if target_table is None:
            target_table = self._meta.db_table
        if target_values is None:
            target_values = [self.pk]
        # If one of the targets is in this tuple, then we must recursively call _cascade_delete
        # because this is a second level of indirection to get to data:
        # Provider ---> <branch-table> ---> x...
        # Make sure that any table(s) in the public schema are first.
        _cascade_branch_tables = (
            "reporting_common_costusagereportmanifest",
            f"reporting_{self._normalized_type}costentrybill",
            f"reporting_{self._normalized_type}meter",
            f"reporting_{self._normalized_type}usagereportperiod",
            "reporting_ocp_clusters",
            "reporting_tenant_api_provider",
        )

        for target_info in self._get_linked_table_names(target_table, public_schema):
            _target_vals = tuple(target_info[k] for k in sorted(target_info))
            if _target_vals in seen:
                continue

            seen.add(_target_vals)
            if target_info["table_name"] == "api_providerinfrastructuremap":
                self._set_infrastructure_id_null()

            if target_info["table_name"] in _cascade_branch_tables:
                # Keep the slice up-tp-date with the number of public schema table names in _cascade_branch_tables
                public_schema = (
                    self.customer.schema_name if target_info["table_name"] in _cascade_branch_tables[1:] else "public"
                )
                LOG.debug(f"DELETE CASCADE BRANCH TO {target_info['table_name']}")
                self._cascade_delete(
                    target_table=target_info["table_name"],
                    target_values=self._get_sub_target_values(target_info, target_values),
                    public_schema=public_schema,
                    seen=seen,
                )
                LOG.debug("DELETE CASCADE BRANCH COPLETE")
            else:
                public_schema = "public"
            self._delete_from_target(target_info, target_values)

    def _set_infrastructure_id_null(self):
        # Because infrastructure is tied to a provider and the infrastructure_id
        # can be shared among other providers, we must set the api_provider.infrastructure_id to null
        # for the infrastructure_id targeted for delete that is shared across other providers.
        # That is a confusing sentence to describe a circular relation between tables.
        _sql = """
update public.api_provider p
   set infrastructure_id = %s
  from public.api_providerinfrastructuremap m
 where m.infrastructure_provider_id = %s::uuid
   and p.infrastructure_id = m.id
;
"""
        LOG.info(
            "Setting the infrastructure_id to null for any provider "
            + "records that link to the target infrastructure map records"
        )
        params = (None, self.pk)
        with connection.cursor() as cur:
            cur.execute(_sql, params)

    def _get_linked_table_names(self, target_table, public_schema):
        """Given a table name and schema name and type,
        find the other tables that are related by foreign keys"""
        with connection.cursor() as cur:
            link_table_sql = """
select ftn.nspname as "table_schema",
       ft.relname as "table_name",
       fc.attname as "column_name"
  from pg_class t
  join pg_constraint con
    on con.confrelid = t.oid
  join pg_attribute fc
    on fc.attrelid = con.conrelid
   and fc.attnum = any(con.conkey::int[])
  join pg_class ft
    on ft.oid = con.conrelid
  join pg_namespace tn
    on tn.oid = t.relnamespace
  join pg_namespace ftn
    on ftn.oid = ft.relnamespace
 where t.relname = %(target_table)s
   and tn.nspname = %(public_schema)s
   and con.contype = %(fk_constraint)s
   and ftn.nspname in (%(public_schema)s, %(search_schema)s)
   and ft.relkind = any(%(relkind)s)
   and not ft.relispartition
   and (
         ft.relname ~ %(type_fregex)s or
         ft.relname ~ %(ocptype_fregex)s or
         ft.relname ~ %(rpt_common_fregex)s or
         ft.relname ~ %(rpt_ingress_fregex)s or
         ft.relname ~ %(rpt_provider_fregex)s or
         ft.relname ~ %(rpt_subs_fregex)s or
         ft.relname ~ %(api_fregex)s
       )
 order
    by case when ft.relname ~ %(tenant_provider_sregex)s then %(tenant_provider_sval)s
            when ft.relname ~ %(ui_table_sregex)s then %(ui_table_sval)s
            when ft.relname ~ %(ocp_type_sregex)s then %(ocp_type_sval)s
            when ft.relname ~ %(daily_summ_sregex)s then %(daily_summ_sval)s
            when ft.relname ~ %(api_sregex)s then %(api_sval)s
            else %(default_sval)s
       end::int,
       ft.relname
;
"""
            params = {
                "relkind": ["p", "r"],
                "fk_constraint": "f",
                "target_table": target_table,
                "public_schema": public_schema,
                "search_schema": self.customer.schema_name,
                "type_fregex": f"_{self._normalized_type}",
                "ocptype_fregex": f"_ocp({self._normalized_type}|all)",
                "rpt_common_fregex": "^reporting_common_",
                "rpt_ingress_fregex": "^reporting_ingressreports",
                "rpt_provider_fregex": "^reporting_tenant_api_provider",
                "rpt_subs_fregex": "^reporting_subs",
                "api_fregex": "^api_",
                "tenant_provider_sregex": "^reporting_tenant_api_provider",
                "tenant_provider_sval": 1,
                "ui_table_sregex": f"^reporting_{self._normalized_type}_",
                "ui_table_sval": 2,
                "ocp_type_sregex": f"^reporting_ocp({self._normalized_type}|all)",
                "ocp_type_sval": 3,
                "daily_summ_sregex": "_daily_summary",
                "daily_summ_sval": 4,
                "api_sregex": "^api_",
                "api_sval": 10,
                "default_sval": 5,
            }
            rendered_sql = cur.mogrify(link_table_sql, params).decode("utf-8")
            LOG.debug(rendered_sql)
            cur.execute(rendered_sql)
            cols = tuple(d[0] for d in cur.description)
            link_tables = [dict(zip(cols, rec)) for rec in cur]

        return link_tables

    def _delete_from_target(self, target_info, target_values=None):
        """Generates and executes a simple delete statement"""
        if target_values is None:
            target_values = [self.uuid]

        qual_table_name = f'''"{target_info['table_schema']}"."{target_info["table_name"]}"'''
        _sql = f"""
delete
  from {qual_table_name}
 where "{target_info["column_name"]}" = any(%s)
;
"""
        with transaction.get_connection().cursor() as cur:
            LOG.info(f"Attempting to delete records from {qual_table_name}")
            cur.execute(_sql, (target_values,))
            LOG.info(f"Deleted {cur.rowcount} records from {qual_table_name}")


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

    org_id = models.TextField(null=True)

    # Provider type (i.e. AWS, OCP, AZURE)
    source_type = models.TextField(null=False)

    # Provider authentication (AWS roleARN, OCP Sources UID, etc.)
    authentication = JSONField(null=False, default=dict)

    # Provider billing source (AWS S3 bucket)
    billing_source = JSONField(null=True, default=dict)

    # Unique identifier for koku Provider
    koku_uuid = models.TextField(null=True, unique=True)

    # This allows us to convenitently join source and provider tables with
    # The Django ORM without using a real database foreign key constraint
    provider = models.ForeignKey("Provider", null=True, on_delete=models.DO_NOTHING, db_constraint=False)

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
    additional_context = JSONField(null=True, default=dict)

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

    class Meta:
        unique_together = ("infrastructure_type", "infrastructure_provider")

    infrastructure_type = models.CharField(max_length=50, choices=Provider.CLOUD_PROVIDER_CHOICES, blank=False)
    infrastructure_provider = models.ForeignKey("Provider", on_delete=models.CASCADE)
