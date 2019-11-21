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
            and provider.billing_source and provider.authentication
            and not provider.koku_uuid):
        return True
    return False


def _ocp_provider_ready_for_create(provider):
    """Determine if OCP provider is ready for provider creation."""
    if (provider.source_id and provider.name and provider.authentication
            and provider.auth_header and not provider.koku_uuid):
        return True
    return False


def _azure_provider_ready_for_create(provider):
    """Determine if AZURE provider is ready for provider creation."""
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


def load_providers_to_update():
    """
    Build a list of Sources have pending Koku Provider updates.

    Args:
        None

    Returns:
        [Dict] - List of events that can be processed by the synchronize_sources method.

    """
    providers_to_update = []
    providers = Sources.objects.filter(pending_update=True, pending_delete=False,
                                       koku_uuid__isnull=False).all()
    for provider in providers:
        providers_to_update.append({'operation': 'update', 'provider': provider})

    return providers_to_update


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


def enqueue_source_delete(source_id):
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
    except Sources.DoesNotExist:
        LOG.error('Unable to enqueue source delete.  %s not found.', str(source_id))


def enqueue_source_update(source_id):
    """
    Queues a source update event to be processed by the synchronize_sources method.

    Args:
        source_id (Integer) - Platform-Sources identifier.

    Returns:
        None

    """
    try:
        source = Sources.objects.get(source_id=source_id)
        if source.koku_uuid and not source.pending_delete:
            source.pending_update = True
            source.save(update_fields=['pending_update'])
    except Sources.DoesNotExist:
        LOG.error('Unable to enqueue source delete.  %s not found.', str(source_id))


def clear_update_flag(source_id):
    """
    Clear pending update flag after successfully updating Koku provider.

    Args:
        source_id (Integer) - Platform-Sources identifier.

    Returns:
        None

    """
    try:
        source = Sources.objects.get(source_id=source_id)
        if source.koku_uuid:
            source.pending_update = False
            source.save()
    except Sources.DoesNotExist:
        LOG.error('Unable to enqueue source delete.  %s not found.', str(source_id))


def create_provider_event(source_id, auth_header, offset):
    """
    Create a Sources database object.

    Args:
        source_id (Integer) - Platform-Sources identifier
        auth_header (String) - HTTP Authentication Header
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


def get_source_type(source_id):
    """Get Source Type from Source ID."""
    source_type = None
    try:
        query = Sources.objects.get(source_id=source_id)
        source_type = query.source_type
    except Sources.DoesNotExist:
        LOG.error('Unable to get Source Type.  Source ID: %s does not exist', str(source_id))
    return source_type


def get_source_from_endpoint(endpoint_id):
    """Get Source ID from Endpoint ID."""
    source_id = None
    try:
        query = Sources.objects.get(endpoint_id=endpoint_id)
        source_id = query.source_id
    except Sources.DoesNotExist:
        LOG.debug('Unable to find Source ID from Endpoint ID: %s', str(endpoint_id))
    return source_id


def add_provider_sources_auth_info(source_id, authentication):
    """
    Add additional Sources information to a Source database object.

    Args:
        source_id (Integer) - Platform-Sources identifier
        authentication (String) - OCP: Sources UID, AWS: RoleARN, etc.

    Returns:
        None

    """
    try:
        query = Sources.objects.get(source_id=source_id)
        current_auth_dict = query.authentication
        subscription_id = current_auth_dict.get('credentials', {}).get('subscription_id')
        if subscription_id and authentication.get('credentials'):
            authentication['credentials']['subscription_id'] = subscription_id
        query.authentication = authentication
        query.save()
    except Sources.DoesNotExist:
        LOG.error('Unable to add authentication details.  Source ID: %s does not exist', str(source_id))


def add_provider_sources_network_info(source_id, source_uuid, name, source_type, endpoint_id):
    """
    Add additional Sources information to a Source database object.

    Args:
        source_id (Integer) - Platform-Sources identifier
        source_uuid (UUID) - Platform-Sources uid
        name (String) - Source name
        source_type (String) - Source type. i.e. AWS, OCP, Azure

    Returns:
        None

    """
    try:
        query = Sources.objects.get(source_id=source_id)
        query.name = name
        query.source_uuid = source_uuid
        query.source_type = source_type
        query.endpoint_id = endpoint_id
        query.save()
    except Sources.DoesNotExist:
        LOG.error('Unable to add network details.  Source ID: %s does not exist', str(source_id))


def get_query_from_api_data(request_data):
    """Get database query based on request_data from API."""
    source_id = request_data.get('source_id')
    source_name = request_data.get('source_name')
    if source_id and source_name:
        raise SourcesStorageError('Expected either source_id or source_name, not both.')
    try:
        if source_id:
            query = Sources.objects.get(source_id=source_id)
        if source_name:
            query = Sources.objects.get(name=source_name)
    except Sources.DoesNotExist:
        raise SourcesStorageError('Source does not exist')
    return query


def add_subscription_id_to_credentials(request_data, subscription_id):
    """
    Add AZURE subscription_id Sources database object.

    Args:
        request_data (dict) - Dictionary containing either source_id or source_name
        subscription_id (String) - Subscription ID

    Returns:
        None

    """
    try:
        query = get_query_from_api_data(request_data)
        if query.source_type not in ('AZURE',):
            raise SourcesStorageError('Source is not AZURE.')
        auth_dict = query.authentication
        if not auth_dict.get('credentials'):
            raise SourcesStorageError('Missing credentials key')
        auth_dict['credentials']['subscription_id'] = subscription_id
        query.authentication = auth_dict
        if query.koku_uuid:
            query.pending_update = True
            query.save(update_fields=['authentication', 'pending_update'])
        else:
            query.save()
    except Sources.DoesNotExist:
        raise SourcesStorageError('Source does not exist')


def _validate_billing_source(provider_type, billing_source):
    """Validate billing source parameters."""
    if provider_type == 'AWS':
        if not billing_source.get('bucket'):
            raise SourcesStorageError('Missing AWS bucket.')
    elif provider_type == 'AZURE':
        data_source = billing_source.get('data_source')
        if not data_source:
            raise SourcesStorageError('Missing AZURE data_source.')
        if not data_source.get('resource_group'):
            raise SourcesStorageError('Missing AZURE resource_group')
        if not data_source.get('storage_account'):
            raise SourcesStorageError('Missing AZURE storage_account')


def add_provider_billing_source(request_data, billing_source):
    """
    Add AWS or AZURE billing source to Sources database object.

    Args:
        request_data (dict) - Dictionary containing either source_id or source_name
        billing_source (String) - S3 bucket

    Returns:
        None

    """
    try:
        query = get_query_from_api_data(request_data)
        if query.source_type not in ('AWS', 'AZURE'):
            raise SourcesStorageError('Source is not AWS nor AZURE.')
        _validate_billing_source(query.source_type, billing_source)
        query.billing_source = billing_source
        if query.koku_uuid:
            query.pending_update = True
            query.save(update_fields=['billing_source', 'pending_update'])
        else:
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
