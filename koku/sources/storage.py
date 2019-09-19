#
# Copyright 2019 Red Hat, Inc.
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
"""Database accessors for Sources database table."""
import logging

from api.provider.models import Sources

LOG = logging.getLogger(__name__)


class SourcesStorageError(Exception):
    """Sources Storage error."""


def _aws_provider_ready_for_create(provider):
    """Determine if AWS provider is ready for provider creation."""
    if (provider.source_id and provider.name and provider.auth_header
            and provider.billing_source and not provider.koku_uuid):
        return True
    return False


def _ocp_provider_ready_for_create(provider):
    """Determine if AWS provider is ready for provider creation."""
    if (provider.source_id and provider.name
            and provider.auth_header and not provider.koku_uuid):
        return True
    return False


def _azure_provider_ready_for_create(provider):
    """Determine if AWS provider is ready for provider creation."""
    if (provider.source_id and provider.name and provider.auth_header
            and provider.billing_source and not provider.koku_uuid):
        billing_source = provider.billing_source.get('data_source', {})
        authentication = provider.authentication.get('credentials', {})
        required_auth_keys = ['client_id', 'tenant_id', 'client_secret', 'subscription_id']
        required_billing_keys = ['resource_group', 'storage_account']
        if set(billing_source.keys()) == set(required_billing_keys)\
                and set(authentication.keys()) == set(required_auth_keys):
            return True
    return False


def screen_and_build_provider_sync_create_event(provider):
    """Determine if the source should be queued for synchronization."""
    provider_event = {}
    screen_map = {'AWS': _aws_provider_ready_for_create,
                  'OCP': _ocp_provider_ready_for_create,
                  'AZURE': _azure_provider_ready_for_create}
    screen_fn = screen_map.get(provider.source_type)
    if screen_fn and screen_fn(provider):
        provider_event = {'operation': 'create', 'provider': provider, 'offset': provider.offset}
    return provider_event


def load_providers_to_create():
    """
    Build a list of Sources that has all information needed to create a Koku Provider.

    This information can come in over several API calls.  The primary use cases where this
    is needed is for side-loading the AWS S3 bucket via the /billing_source API and for
    re-loading the process queue when the service goes down before synchronization could be
    completed.

    Args:
        None

    Returns:
        [Dict] - List of events that can be processed by the synchronize_sources method.

    """
    providers_to_create = []
    all_providers = Sources.objects.all()
    for provider in all_providers:
        source_event = screen_and_build_provider_sync_create_event(provider)
        if source_event:
            providers_to_create.append(source_event)

    return providers_to_create


def load_providers_to_delete():
    """
    Build a list of Sources that need to be deleted from the Koku provider database.

    The primary use case where this is when the Koku API is down and the Source has
    been removed from the Platform-Sources backend.  Additionally this is also needed
    to re-load the process queue when the service goes down before synchronization
    could be completed.

    Args:
        None

    Returns:
        [Dict] - List of events that can be processed by the synchronize_sources method.

    """
    providers_to_delete = []
    all_providers = Sources.objects.all()
    for provider in all_providers:
        if provider.pending_delete:
            providers_to_delete.append({'operation': 'destroy',
                                        'provider': provider,
                                        'offset': provider.offset})
    return providers_to_delete


async def enqueue_source_delete(queue, source_id):
    """
    Queues a source destroy event to be processed by the synchronize_sources method.

    Args:
        queue (Asyncio Queue) - process_queue containing all pending Souces-koku events.
        source_id (Integer) - Platform-Sources identifier.

    Returns:
        None

    """
    try:
        source = Sources.objects.get(source_id=source_id)
        source.pending_delete = True
        source.save()
        await queue.put({'operation': 'destroy', 'provider': source})
    except Sources.DoesNotExist:
        LOG.error('Unable to enqueue source delete.  %s not found.', str(source_id))


def create_provider_event(source_id, auth_header, offset):
    """
    Create a Sources database object.

    Args:
        source_id (Integer) - Platform-Sources identifier
        auth_header (String) - HTTP Authenticaiton Header
        offset (Integer) - Kafka offset

    Returns:
        None

    """
    try:
        query = Sources.objects.get(source_id=source_id)
        query.auth_header = auth_header
        query.offset = offset
        query.save()
    except Sources.DoesNotExist:
        new_event = Sources(source_id=source_id, auth_header=auth_header, offset=offset)
        new_event.save()


def destroy_provider_event(source_id):
    """
    Destroy a Sources database object.

    Args:
        source_id (Integer) - Platform-Sources identifier

    Returns:
        None

    """
    koku_uuid = None
    try:
        query = Sources.objects.get(source_id=source_id)
        koku_uuid = query.koku_uuid
        query.delete()
    except Sources.DoesNotExist:
        LOG.error('Unable to delete.  Source ID: %s does not exist', str(source_id))

    return koku_uuid


def add_provider_sources_network_info(source_id, name, source_type, authentication):
    """
    Add additional Sources information to a Source database object.

    Args:
        source_id (Integer) - Platform-Sources identifier
        name (String) - Source name
        source_type (String) - Source type. i.e. AWS, OCP, Azure
        authentication (String) - OCP: Sources UID, AWS: RoleARN, etc.

    Returns:
        None

    """
    try:
        query = Sources.objects.get(source_id=source_id)
        query.name = name
        query.source_type = source_type
        query.authentication = authentication
        query.save()
    except Sources.DoesNotExist:
        LOG.error('Unable to add network details.  Source ID: %s does not exist', str(source_id))


def add_subscription_id_to_credentials(source_id, subscription_id):
    """
    Add AZURE subscription_id Sources database object.

    Args:
        source_id (Integer) - Platform-Sources identifier
        subscription_id (String) - Subscription ID

    Returns:
        None

    """
    try:
        query = Sources.objects.get(source_id=source_id)
        if query.source_type not in ('AZURE',):
            raise SourcesStorageError('Source is not AZURE.')
        auth_dict = query.authentication
        auth_dict['credentials']['subscription_id'] = subscription_id
        query.authentication = auth_dict
        query.save()
    except Sources.DoesNotExist:
        raise SourcesStorageError('Source does not exist')


def add_provider_billing_source(source_id, billing_source):
    """
    Add AWS or AZURE billing source to Sources database object.

    Args:
        source_id (Integer) - Platform-Sources identifier
        billing_source (String) - S3 bucket

    Returns:
        None

    """
    try:
        query = Sources.objects.get(source_id=source_id)
        if query.source_type not in ('AWS', 'AZURE'):
            raise SourcesStorageError('Source is not AWS nor AZURE.')
        query.billing_source = billing_source
        query.save()
    except Sources.DoesNotExist:
        raise SourcesStorageError('Source does not exist')


def add_provider_koku_uuid(source_id, koku_uuid):
    """
    Add Koku provider UUID to Sources database object.

    Args:
        source_id (Integer) - Platform-Sources identifier
        koku_uuid (String) - Koku Provider UUID.

    Returns:
        None

    """
    try:
        query = Sources.objects.get(source_id=source_id)
        query.koku_uuid = koku_uuid
        query.save()
    except Sources.DoesNotExist:
        LOG.error('%s does not exist', str(source_id))
