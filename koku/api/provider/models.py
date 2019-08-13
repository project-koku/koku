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

from uuid import uuid4

from django.conf import settings
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.db.models.constraints import CheckConstraint


class ProviderAuthentication(models.Model):
    """A Koku Provider Authentication.

    Used for accessing cost providers data like AWS Accounts.
    """

    uuid = models.UUIDField(default=uuid4, editable=False,
                            unique=True, null=False)

    # XXX: This field is DEPRECATED
    # XXX: the credentials field should be used instead.
    # Ex: AWS ARN for cross-acount role access
    provider_resource_name = models.TextField(null=True, unique=True)

    credentials = JSONField(null=True, default=dict)

    # pylint: disable=too-few-public-methods
    class Meta:
        """Meta class."""
        # The goal is to ensure that exactly one field is not null.
        constraints = [
            # NOT (provider_resource_name IS NULL AND credentials IS NULL)
            CheckConstraint(
                check=~models.Q(models.Q(provider_resource_name=None) \
                                & models.Q(credentials={})),
                name='credentials_and_resource_name_both_null'
            ),
            # NOT (provider_resource_name IS NOT NULL AND credentials IS NOT NULL)
            CheckConstraint(
                check=~models.Q(~models.Q(provider_resource_name=None) \
                                & ~models.Q(credentials={})),
                name='credentials_and_resource_name_both_not_null'
            ),
        ]


class ProviderBillingSource(models.Model):
    """A Koku Provider Billing Source.

    Used for accessing cost providers billing sourece like AWS Account S3.
    """

    uuid = models.UUIDField(default=uuid4, editable=False,
                            unique=True, null=False)

    # XXX: This field is DEPRECATED
    # XXX: the data_source field should be used instead.
    bucket = models.CharField(max_length=63, null=True)

    data_source = JSONField(null=True, default=dict)

    # pylint: disable=too-few-public-methods
    class Meta:
        """Meta class."""
        # The goal is to ensure that exactly one field is not null.
        constraints = [
            # NOT (bucket IS NULL AND data_source IS NULL)
            CheckConstraint(
                check=~models.Q(models.Q(bucket=None) \
                                & models.Q(data_source={})),
                name='bucket_and_data_sourcce_both_null'
            ),
            # NOT (bucket IS NOT NULL AND data_source IS NOT NULL)
            CheckConstraint(
                check=~models.Q(~models.Q(bucket=None) \
                                & ~models.Q(data_source={})),
                name='bucket_and_data_sourcce_both_not_null'
            ),
        ]


class Provider(models.Model):
    """A Koku Provider.

    Used for modeling cost providers like AWS Accounts.
    """

    # pylint: disable=too-few-public-methods
    class Meta:
        """Meta for Provider."""

        ordering = ['name']
        unique_together = ('authentication', 'billing_source')

    PROVIDER_AWS = 'AWS'
    PROVIDER_OCP = 'OCP'
    PROVIDER_AZURE = 'AZURE'

    if settings.DEBUG:
        PROVIDER_AWS_LOCAL = 'AWS-local'
        PROVIDER_OCP_LOCAL = 'OCP-local'
        PROVIDER_CHOICES = ((PROVIDER_AWS, PROVIDER_AWS),
                            (PROVIDER_OCP, PROVIDER_OCP),
                            (PROVIDER_AZURE, PROVIDER_AZURE),
                            (PROVIDER_AWS_LOCAL, PROVIDER_AWS_LOCAL),
                            (PROVIDER_OCP_LOCAL, PROVIDER_OCP_LOCAL),)
    else:
        PROVIDER_CHOICES = ((PROVIDER_AWS, PROVIDER_AWS),
                            (PROVIDER_OCP, PROVIDER_OCP),
                            (PROVIDER_AZURE, PROVIDER_AZURE))

    uuid = models.UUIDField(default=uuid4, editable=False,
                            unique=True, null=False)
    name = models.CharField(max_length=256, null=False)
    type = models.CharField(max_length=50, null=False,
                            choices=PROVIDER_CHOICES, default=PROVIDER_AWS)
    authentication = models.ForeignKey('ProviderAuthentication', null=True,
                                       on_delete=models.DO_NOTHING)
    billing_source = models.ForeignKey('ProviderBillingSource', null=True,
                                       on_delete=models.DO_NOTHING, blank=True)
    customer = models.ForeignKey('Customer', null=True,
                                 on_delete=models.PROTECT)
    created_by = models.ForeignKey('User', null=True,
                                   on_delete=models.SET_NULL)
    setup_complete = models.BooleanField(default=False)
    created_timestamp = models.DateTimeField(auto_now_add=True, blank=True, null=True)


class ProviderStatus(models.Model):
    """Koku provider status.

    Used for tracking provider status.

    """

    # Provider states used to signal whether the Provider is suitable for
    # attempting to download and process reports.
    #
    # These states are duplicated in masu.database.provider_db_accessor
    #
    STATES = ((0, 'New'),
              (1, 'Ready'),
              (33, 'Warning'),
              (98, 'Disabled: Error'),
              (99, 'Disabled: Admin'),)

    provider = models.ForeignKey('Provider', null=False,
                                 on_delete=models.CASCADE, blank=False)
    status = models.IntegerField(null=False,
                                 choices=STATES,
                                 default=0)
    last_message = models.CharField(max_length=256, null=False)
    timestamp = models.DateTimeField()
    retries = models.IntegerField(null=False, default=0)
