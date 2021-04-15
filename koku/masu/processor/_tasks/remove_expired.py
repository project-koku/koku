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
"""Remove expired data asynchronous tasks."""
import logging

from masu.processor.expired_data_remover import ExpiredDataRemover

LOG = logging.getLogger(__name__)


def _remove_expired_data(schema_name, provider, simulate, provider_uuid=None, line_items_only=False):
    """
    Task to remove expired data.

    Args:
        schema_name (String) db schema name
        provider    (String) provider type
        simulate    (Boolean) Simulate report data removal

    Returns:
        None

    """
    log_statement = (
        f"Remove expired data:\n"
        f" schema_name: {schema_name}\n"
        f" provider: {provider}\n"
        f" simulate: {simulate}\n"
        f" line_items_only: {line_items_only}\n"
    )
    LOG.info(log_statement)

    remover = ExpiredDataRemover(schema_name, provider)
    removed_data = remover.remove(simulate=simulate, provider_uuid=provider_uuid, line_items_only=line_items_only)
    if removed_data:
        status_msg = "Expired Data" if simulate else "Removed Data"
        result_msg = f"{status_msg}:\n {str(removed_data)}"
        LOG.info(result_msg)
