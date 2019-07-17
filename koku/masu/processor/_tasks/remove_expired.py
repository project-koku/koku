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

from celery.utils.log import get_task_logger

from masu.processor.expired_data_remover import ExpiredDataRemover

LOG = get_task_logger(__name__)


def _remove_expired_data(schema_name, provider, simulate, provider_id=None):
    """
    Task to remove expired data.

    Args:
        schema_name (String) db schema name
        provider    (String) provider type
        simulate    (Boolean) Simulate report data removal

    Returns:
        None

    """
    stmt = ('Remove expired data:'
            ' schema_name: {},'
            ' simulate: {}')
    log_statement = stmt.format(schema_name,
                                simulate)
    LOG.info(log_statement)

    remover = ExpiredDataRemover(schema_name, provider)
    removed_data = remover.remove(simulate=simulate, provider_id=provider_id)

    status_msg = 'Expired Data' if simulate else 'Removed Data'
    result_msg = '{}: {}'.format(status_msg, str(removed_data))
    LOG.info(result_msg)
