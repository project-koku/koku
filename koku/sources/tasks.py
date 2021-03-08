#
# Copyright 2021 Red Hat, Inc.
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
"""Tasks for sources-client."""
import logging

from koku import celery_app
from sources.sources_provider_coordinator import SourcesProviderCoordinator

LOG = logging.getLogger(__name__)


@celery_app.task(name="sources.tasks.delete_source", queue="remove_expired")
def delete_source(source_id, auth_header, koku_uuid):
    """Delete Provider and Source."""
    LOG.info(f"Deleting Provider {koku_uuid} for Source ID: {source_id}")
    coordinator = SourcesProviderCoordinator(source_id, auth_header)
    coordinator.destroy_account(koku_uuid)
