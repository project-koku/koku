#
# Copyright 2018 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""API models for import organization."""
# flake8: noqa
# pylint: disable=unused-import
from django.db import models

from api.status.models import Status
from api.iam.models import Customer, ResetToken, Tenant, User, UserPreference
from api.provider.models import (Provider,
                                 ProviderAuthentication,
                                 ProviderBillingSource)


class CostUsageReportStatus(models.Model):
    """Information on the state of the cost usage report."""

    provider = models.ForeignKey('Provider', null=True,
                                 on_delete=models.CASCADE)
    report_name = models.CharField(max_length=128, null=False, unique=True)
    cursor_position = models.PositiveIntegerField()
    last_completed_datetime = models.DateTimeField(null=True)
    last_started_datetime = models.DateTimeField(null=True)
    etag = models.CharField(max_length=64, null=True)
