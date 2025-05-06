#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Remove expired report data."""
import logging
from datetime import datetime
from datetime import timedelta

from django.conf import settings

from api.common import log_json
from api.models import Provider
from api.utils import DateHelper
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor.aws.aws_report_db_cleaner import AWSReportDBCleaner
from masu.processor.azure.azure_report_db_cleaner import AzureReportDBCleaner
from masu.processor.gcp.gcp_report_db_cleaner import GCPReportDBCleaner
from masu.processor.ocp.ocp_report_db_cleaner import OCPReportDBCleaner

LOG = logging.getLogger(__name__)


class ExpiredDataRemoverError(Exception):
    """Expired Data Removalerror."""

    pass


class ExpiredDataRemover:
    """
    Removes expired report data based on masu's retention policy.

    Retention policy can be configured via environment variable.

    """

    def __init__(self, customer_schema, provider, num_of_months_to_keep=None, line_items_month_to_keep=None):
        """
        Initializer.

        Args:
            customer_schema (String): Schema name for given customer.
            num_of_months_to_keep (Int): Number of months to retain in database.

        """
        self._schema = customer_schema
        self._provider = provider
        self._months_to_keep = num_of_months_to_keep
        if self._months_to_keep is None:
            self._months_to_keep = Config.MASU_RETAIN_NUM_MONTHS
        self._line_items_months = line_items_month_to_keep
        if self._line_items_months is None:
            self._line_items_months = Config.MASU_RETAIN_NUM_MONTHS_LINE_ITEM_ONLY
        try:
            self._cleaner = self._set_cleaner()
        except Exception as err:
            raise ExpiredDataRemoverError(str(err))

        if not self._cleaner:
            raise ExpiredDataRemoverError("Invalid provider type specified.")

    def _set_cleaner(self):
        """
        Create the expired report data object.

        Object is specific to the report provider.

        Args:
            None

        Returns:
            (Object) : Provider-specific report cleaner

        """
        if self._provider in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
            return AWSReportDBCleaner(self._schema)
        if self._provider in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
            return AzureReportDBCleaner(self._schema)
        if self._provider in (Provider.PROVIDER_OCP,):
            return OCPReportDBCleaner(self._schema)
        if self._provider in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
            return GCPReportDBCleaner(self._schema)

        return None

    def _calculate_expiration_date(self):
        """
        Calculate the expiration date based on the retention policy.

        Args:
            None

        Returns:
            (datetime.datetime) Expiration date

        """
        months = self._months_to_keep
        expiration_msg = "Report data expiration is {} for a {} month retention policy"
        today = DateHelper().today
        LOG.info("Current date time is %s", today)

        middle_of_current_month = today.replace(day=15)
        num_of_days_to_expire_date = months * timedelta(days=30)
        middle_of_expire_date_month = middle_of_current_month - num_of_days_to_expire_date
        expiration_date = datetime(
            year=middle_of_expire_date_month.year,
            month=middle_of_expire_date_month.month,
            day=1,
            tzinfo=settings.UTC,
        )
        msg = expiration_msg.format(expiration_date, months)
        LOG.info(msg)
        return expiration_date

    def remove(self, simulate=False, provider_uuid=None):
        """
        Remove expired data based on the retention policy.

        Also remove expired CostUsageReportManifests, regardless of Provider type.

        Args:
            None

        Returns:
            ([{}]) List of dictionaries containing 'account_payer_id' and 'billing_period_start'

        """
        removed_data = []
        if provider_uuid is not None:
            removed_data = self._cleaner.purge_expired_report_data(simulate=simulate, provider_uuid=provider_uuid)
            with ReportManifestDBAccessor() as manifest_accessor:
                # Remove expired CostUsageReportManifests
                expiration_date = self._calculate_expiration_date()
                if not simulate:
                    manifest_accessor.purge_expired_report_manifest_provider_uuid(provider_uuid, expiration_date)
                LOG.info(
                    log_json(
                        msg="Removed CostUsageReportManifest",
                        provider_uuid=provider_uuid,
                        expiration_date=expiration_date,
                    )
                )
        else:
            expiration_date = self._calculate_expiration_date()
            # Remove expired CostUsageReportManifests
            removed_data = self._cleaner.purge_expired_report_data(expired_date=expiration_date, simulate=simulate)
            with ReportManifestDBAccessor() as manifest_accessor:
                if not simulate:
                    manifest_accessor.purge_expired_report_manifest(self._provider, expiration_date)
                LOG.info(
                    log_json(
                        msg="Removed CostUsageReportManifest", provider=self._provider, expiration_date=expiration_date
                    )
                )
        return removed_data

    def remove_expired_trino_partitions(self, simulate=False):
        """
        Removes expired trino partitions based on the retention policy.
        """
        if self._provider != Provider.PROVIDER_OCP:
            LOG.info(f"{Provider.PROVIDER_OCP} is the only supported type for removing trino partitions.")
            return
        removed_partitions = []
        expiration_date = self._calculate_expiration_date()
        removed_partitions = self._cleaner.purge_expired_trino_partitions(
            expired_date=expiration_date, simulate=simulate
        )
        return removed_partitions
