#
# Copyright 2020 Red Hat, Inc.
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
"""GCP utility functions and vars."""
import datetime
import json
import logging
from json.decoder import JSONDecodeError

from tenant_schemas.utils import schema_context

from api.models import Provider
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor

LOG = logging.getLogger(__name__)

GCP_SERVICE_LINE_ITEM_TYPE_MAP = {
    "Compute Engine": "usage",
    "Kubernetes Engine": "usage",
    "Cloud Functions": "usage",
    "Clould Run": "usage",
    "VMware Engine": "usage",
    "Filestore": "storage",
    "Storage": "storage",
    "Cloud Storage": "storage",
    "Data Transfer": "storage",
    "VPC network": "network",
    "Network services": "network",
    "Hybrid Connectivity": "network",
    "Network Service Tiers": "network",
    "Network Security": "network",
    "Network Intelligence": "network",
    "Bigtable": "database",
    "Datastore": "database",
    "Database Migrations": "database",
    "Firestore": "database",
    "MemoryStore": "database",
    "Spanner": "database",
    "SQL": "database",
}


def get_bills_from_provider(provider_uuid, schema, start_date=None, end_date=None):
    """
    Return the GCP bill IDs given a provider UUID.

    Args:
        provider_uuid (str): Provider UUID.
        schema (str): Tenant schema
        start_date (datetime, str): Start date for bill IDs.
        end_date (datetime, str) End date for bill IDs.

    Returns:
        (list): GCP cost entry bill objects.

    """
    if isinstance(start_date, (datetime.datetime, datetime.date)):
        start_date = start_date.replace(day=1)
        start_date = start_date.strftime("%Y-%m-%d")

    if isinstance(end_date, (datetime.datetime, datetime.date)):
        end_date = end_date.strftime("%Y-%m-%d")

    with ProviderDBAccessor(provider_uuid) as provider_accessor:
        provider = provider_accessor.get_provider()

    if not provider:
        err_msg = "Provider UUID is not associated with a given provider."
        LOG.warning(err_msg)
        return []

    if provider.type not in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
        err_msg = f"Provider UUID is not an GCP type.  It is {provider.type}"
        LOG.warning(err_msg)
        return []

    with GCPReportDBAccessor(schema) as report_accessor:
        with schema_context(schema):
            bills = report_accessor.get_cost_entry_bills_query_by_provider(provider.uuid)
            if start_date:
                bills = bills.filter(billing_period_start__gte=start_date)
            if end_date:
                bills = bills.filter(billing_period_start__lte=end_date)
            bills = bills.all()

    return bills


def process_gcp_labels(label_string):
    """Convert the report string to a JSON dictionary.

    Args:
        label_string (str): The raw report string of pod labels

    Returns:
        (dict): The JSON dictionary made from the label string

    """
    label_dict = {}
    try:
        labels = json.loads(label_string.replace("'", '"'))
        label_dict = {entry.get("key"): entry.get("value") for entry in labels}
    except JSONDecodeError:
        LOG.warning("Unable to process GCP labels.")

    return json.dumps(label_dict)


def process_gcp_credits(credit_string):
    """Process the credits column, which is non-standard JSON."""
    credit_dict = {}
    try:
        credits = json.loads(credit_string.replace("'", '"').replace("None", '"None"'))
        if credits:
            credit_dict = credits[0]
    except JSONDecodeError:
        LOG.warning("Unable to process GCP credits.")

    return json.dumps(credit_dict)


def gcp_post_processor(data_frame):
    """Guarantee column order for Azure parquet files"""
    columns = list(data_frame)
    for column in columns:
        if "." in column:
            new_col_name = column.replace(".", "_")
            data_frame[new_col_name] = data_frame[column]
            data_frame = data_frame.drop(columns=[column])
    return data_frame
