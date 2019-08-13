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
"""OCP utility functions."""
import json
import logging
import os

from dateutil import parser
from dateutil.relativedelta import relativedelta

from masu.config import Config
from masu.database.provider_auth_db_accessor import ProviderAuthDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external import (OCP_LOCAL_SERVICE_PROVIDER, OPENSHIFT_CONTAINER_PLATFORM)

LOG = logging.getLogger(__name__)


def get_report_details(report_directory):
    """
    Get OCP usage report details from manifest file.

    Date range is aligned on the first day of the current
    month and ends on the first day of the next month from the
    specified date.

    Args:
        report_directory (String): base directory for report.

    Returns:
        (Dict): keys: value
            "file: String,
             cluster_id: String,
             payload_date: DateTime,
             manifest_path: String,
             uuid: String,
             manifest_path: String"

    """
    manifest_path = '{}/{}'.format(report_directory, 'manifest.json')

    payload_dict = {}
    try:
        with open(manifest_path) as file:
            payload_dict = json.load(file)
            payload_dict['date'] = parser.parse(payload_dict['date'])
            payload_dict['manifest_path'] = manifest_path
    except (OSError, IOError, KeyError) as exc:
        LOG.error('Unable to extract manifest data: %s', exc)

    return payload_dict


def month_date_range(for_date_time):
    """
    Get a formatted date range string for the given date.

    Date range is aligned on the first day of the current
    month and ends on the first day of the next month from the
    specified date.

    Args:
        for_date_time (DateTime): The starting datetime object

    Returns:
        (String): "YYYYMMDD-YYYYMMDD", example: "19701101-19701201"

    """
    start_month = for_date_time.replace(day=1, second=1, microsecond=1)
    end_month = start_month + relativedelta(months=+1)
    timeformat = '%Y%m%d'
    return '{}-{}'.format(start_month.strftime(timeformat),
                          end_month.strftime(timeformat))


def get_local_file_name(file_path):
    """
    Return the local file name for a given report path.

    Args:
        file_path (String): report file path from manifest.

    Returns:
        (String): file name for the local file.

    """
    filename = file_path.split('/')[-1]
    date_range = file_path.split('/')[-2]
    local_file_name = f'{date_range}_{filename}'
    return local_file_name


def get_cluster_id_from_provider(provider_uuid):
    """
    Return the cluster ID given a provider UUID.

    Args:
        provider_uuid (String): provider UUID.

    Returns:
        (String): OpenShift Cluster ID

    """
    cluster_id = None
    with ProviderDBAccessor(provider_uuid) as provider_accessor:
        provider_type = provider_accessor.get_type()

    if provider_type not in (OCP_LOCAL_SERVICE_PROVIDER, OPENSHIFT_CONTAINER_PLATFORM):
        err_msg = 'Provider UUID is not an OpenShift type.  It is {}'.\
            format(provider_type)
        LOG.warning(err_msg)
        return cluster_id

    with ProviderDBAccessor(provider_uuid=provider_uuid) as provider_accessor:
        cluster_id = provider_accessor.get_authentication()

    return cluster_id


def get_provider_uuid_from_cluster_id(cluster_id):
    """
    Return the provider UUID given the cluster ID.

    Args:
        cluster_id (String): OpenShift Cluster ID

    Returns:
        (String): provider UUID

    """
    provider_uuid = None
    auth_id = None
    with ProviderAuthDBAccessor(provider_resource_name=cluster_id) as auth_accessor:
        auth_id = auth_accessor.get_auth_id()
        if auth_id:
            with ProviderDBAccessor(auth_id=auth_id) as provider_accessor:
                provider_uuid = provider_accessor.get_uuid()
    return provider_uuid


def poll_ingest_override_for_provider(provider_uuid):
    """
    Return whether or not the OpenShift provider should be treated like a POLLING provider.

    The purpose of this is to continue to support back-door (no upload service) OpenShift
    report ingest.  Used for development and local test automation.

    On the masu-worker if the insights local directory exists for the given provider then
    the masu orchestrator will treat it as a polling provider rather than listening.

    Args:
        provider_uuid (String): Provider UUID.

    Returns:
        (Boolean): True: OCP provider should be treated like a polling provider.

    """
    cluster_id = get_cluster_id_from_provider(provider_uuid)
    local_ingest_path = '{}/{}'.format(Config.INSIGHTS_LOCAL_REPORT_DIR, str(cluster_id))
    return os.path.exists(local_ingest_path)
