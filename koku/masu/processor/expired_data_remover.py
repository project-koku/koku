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
"""Remove expired report data."""
# pylint: skip-file
# Skipping entire file for now since we are unable to disable duplicate-code lint
# on the masu.external provider name import line.
# See issue https://github.com/PyCQA/pylint/issues/214

import logging
from datetime import (datetime, timedelta)

import pytz

from masu.config import Config
from masu.external import (AMAZON_WEB_SERVICES,
                           AWS_LOCAL_SERVICE_PROVIDER,
                           AZURE,
                           AZURE_LOCAL_SERVICE_PROVIDER,
                           OPENSHIFT_CONTAINER_PLATFORM)
from masu.external.date_accessor import DateAccessor
from masu.processor.aws.aws_report_db_cleaner import AWSReportDBCleaner
from masu.processor.azure.azure_report_db_cleaner import AzureReportDBCleaner
from masu.processor.ocp.ocp_report_db_cleaner import OCPReportDBCleaner

LOG = logging.getLogger(__name__)


class ExpiredDataRemoverError(Exception):
    """Expired Data Removalerror."""

    pass


# pylint: disable=too-few-public-methods
class ExpiredDataRemover():
    """
    Removes expired report data based on masu's retention policy.

    Retention policy can be configured via environment variable.

    """

    def __init__(self, customer_schema, provider,
                 num_of_months_to_keep=None):
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
        self._expiration_date = self._calculate_expiration_date()
        try:
            self._cleaner = self._set_cleaner()
        except Exception as err:
            raise ExpiredDataRemoverError(str(err))

        if not self._cleaner:
            raise ExpiredDataRemoverError('Invalid provider type specified.')

    def _set_cleaner(self):
        """
        Create the expired report data object.

        Object is specific to the report provider.

        Args:
            None

        Returns:
            (Object) : Provider-specific report cleaner

        """
        if self._provider in (AMAZON_WEB_SERVICES, AWS_LOCAL_SERVICE_PROVIDER):
            return AWSReportDBCleaner(self._schema)

        if self._provider in (AZURE, AZURE_LOCAL_SERVICE_PROVIDER):
            return AzureReportDBCleaner(self._schema)

        if self._provider in (OPENSHIFT_CONTAINER_PLATFORM, ):
            return OCPReportDBCleaner(self._schema)

        return None

    def _calculate_expiration_date(self):
        """
        Calculate the expiration date based on the retention policy.

        Args:
            None

        Returns:
            (datetime.datetime) Expiration date

        """
        today = DateAccessor().today()
        LOG.info('Current date time is %s', today)

        middle_of_current_month = today.replace(day=15)
        num_of_days_to_expire_date = self._months_to_keep * timedelta(days=30)
        middle_of_expire_date_month = middle_of_current_month - num_of_days_to_expire_date
        expiration_date = datetime(year=middle_of_expire_date_month.year,
                                   month=middle_of_expire_date_month.month,
                                   day=1,
                                   tzinfo=pytz.UTC)
        expiration_msg = 'Report data expiration is {} for a {} month retention policy'
        msg = expiration_msg.format(expiration_date, self._months_to_keep)
        LOG.info(msg)
        return expiration_date

    def remove(self, simulate=False, provider_id=None):
        """
        Remove expired data based on the retention policy.

        Args:
            None

        Returns:
            ([{}]) List of dictionaries containing 'account_payer_id' and 'billing_period_start'

        """
        if provider_id is not None:
            removed_data = self._cleaner.purge_expired_report_data(
                simulate=simulate,
                provider_id=provider_id
            )
        else:
            expiration_date = self._calculate_expiration_date()
            removed_data = self._cleaner.purge_expired_report_data(
                expired_date=expiration_date,
                simulate=simulate
            )
        return removed_data
