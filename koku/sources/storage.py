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
import binascii
import logging
from base64 import b64decode
from json import loads as json_loads
from json.decoder import JSONDecodeError

from django.db import InterfaceError, connection

from api.provider.models import Provider, Sources


LOG = logging.getLogger(__name__)
REQUIRED_AZURE_AUTH_KEYS = {'client_id', 'tenant_id', 'client_secret', 'subscription_id'}
REQUIRED_AZURE_BILLING_KEYS = {'resource_group', 'storage_account'}


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
        if billing_source and authentication:
            if (
                set(authentication.keys()) == REQUIRED_AZURE_AUTH_KEYS
                and set(billing_source.keys()) == REQUIRED_AZURE_BILLING_KEYS
            ):
                return True
    return False


def screen_and_build_provider_sync_create_event(provider):
    """Determine if the source should be queued for synchronization."""
    provider_event = {}
    screen_map = {Provider.PROVIDER_AWS: _aws_provider_ready_for_create,
                  Provider.PROVIDER_OCP: _ocp_provider_ready_for_create,
                  Provider.PROVIDER_AZURE: _azure_provider_ready_for_create}
    screen_fn = screen_map.get(provider.source_type)
    if screen_fn and screen_fn(provider) and not provider.pending_delete:
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


def get_source(source_id, err):
    """Access Sources, log err on DoesNotExist, close connection on InterfaceError."""
    try:
        return Sources.objects.get(source_id=source_id)
    except Sources.DoesNotExist:
        LOG.error(err)
    except InterfaceError as error:
        LOG.error(f'Closing DB connection. Accessing sources resulted in InterfaceError: {error}')
        connection.close()


def enqueue_source_delete(source_id):
    """
    Queues a source destroy event to be processed by the synchronize_sources method.

    Args:
        queue (Asyncio Queue) - process_queue containing all pending Souces-koku events.
        source_id (Integer) - Platform-Sources identifier.

    Returns:
        None

    """
    source = get_source(source_id, f'Unable to enqueue source delete.  {source_id} not found.')
    if not source.pending_delete:
        source.pending_delete = True
        source.save()


def enqueue_source_update(source_id):
    """
    Queues a source update event to be processed by the synchronize_sources method.

    Args:
        source_id (Integer) - Platform-Sources identifier.

    Returns:
        None

    """
    source = get_source(source_id, f'Unable to enqueue source update.  {source_id} not found.')
    if source and source.koku_uuid and not source.pending_delete and not source.pending_update:
        source.pending_update = True
        source.save(update_fields=['pending_update'])


def clear_update_flag(source_id):
    """
    Clear pending update flag after successfully updating Koku provider.

    Args:
        source_id (Integer) - Platform-Sources identifier.

    Returns:
        None

    """
    source = get_source(source_id, f'Unable to clear update flag.  {source_id} not found.')
    if source and source.koku_uuid and source.pending_update:
        source.pending_update = False
        source.save()


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
        decoded_rh_auth = b64decode(auth_header)
        json_rh_auth = json_loads(decoded_rh_auth)
        account_id = json_rh_auth.get('identity', {}).get('account_number')
    except (binascii.Error, JSONDecodeError) as error:
        LOG.error(str(error))
        return

    try:
        Sources.objects.get(source_id=source_id)
        LOG.debug(f'Source ID {str(source_id)} already exists.')
    except Sources.DoesNotExist:
        new_event = Sources(source_id=source_id, auth_header=auth_header,
                            offset=offset, account_id=account_id)
        new_event.save()
    except InterfaceError as error:
        LOG.error(f'source.storage.create_provider_event InterfaceError {error}')
        connection.close()


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
        source = Sources.objects.get(source_id=source_id)
        koku_uuid = source.koku_uuid
        source.delete()
    except Sources.DoesNotExist:
        LOG.debug('Source ID: %s already removed.', str(source_id))

    return koku_uuid


def update_endpoint_id(source_id, endpoint_id):
    """Update Endpoint ID from Source ID."""
    source = get_source(source_id, f'[update_endpoint_id] Unable to get Source Type.  Source ID: {source_id} does not exist')
    if source:
        source.endpoint_id = endpoint_id
        source.save()


def get_source_type(source_id):
    """Get Source Type from Source ID."""
    source_type = None
    source = get_source(source_id, f'[get_source_type] Unable to get Source Type.  Source ID: {source_id} does not exist')
    if source:
        source_type = source.source_type
    return source_type


def get_source_from_endpoint(endpoint_id):
    """Get Source ID from Endpoint ID."""
    source_id = None
    try:
        query = Sources.objects.get(endpoint_id=endpoint_id)
        source_id = query.source_id
    except Sources.DoesNotExist:
        LOG.debug('Unable to find Source ID from Endpoint ID: %s', str(endpoint_id))
    except InterfaceError as error:
        LOG.error(f'source.storage.get_source_from_endpoint InterfaceError {error}')
        connection.close()
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
    source = get_source(source_id, f'Unable to add authentication details.  Source ID: {source_id} does not exist')
    if source:
        current_auth_dict = source.authentication
        subscription_id = None
        if current_auth_dict.get('credentials', {}):
            subscription_id = current_auth_dict.get('credentials', {}).get('subscription_id')
        if subscription_id and authentication.get('credentials'):
            authentication['credentials']['subscription_id'] = subscription_id
        if source.authentication != authentication:
            source.authentication = authentication
            source.save()


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
    save_needed = False
    source = get_source(source_id, f'Unable to add network details.  Source ID: {source_id} does not exist')
    if source:
        if source.name != name:
            source.name = name
            save_needed = True
        if str(source.source_uuid) != source_uuid:
            source.source_uuid = source_uuid
            save_needed = True
        if source.source_type != source_type:
            source.source_type = source_type
            save_needed = True
        if str(source.endpoint_id) != endpoint_id:
            source.endpoint_id = endpoint_id
            save_needed = True
        if save_needed:
            source.save()


def _validate_billing_source(provider_type, billing_source):
    """Validate billing source parameters."""
    if provider_type == Provider.PROVIDER_AWS:
        if not billing_source.get('bucket'):
            raise SourcesStorageError('Missing AWS bucket.')
    elif provider_type == Provider.PROVIDER_AZURE:
        data_source = billing_source.get('data_source')
        if not data_source:
            raise SourcesStorageError('Missing AZURE data_source.')
        if not data_source.get('resource_group'):
            raise SourcesStorageError('Missing AZURE resource_group')
        if not data_source.get('storage_account'):
            raise SourcesStorageError('Missing AZURE storage_account')


def add_provider_koku_uuid(source_id, koku_uuid):
    """
    Add Koku provider UUID to Sources database object.

    Args:
        source_id (Integer) - Platform-Sources identifier
        koku_uuid (String) - Koku Provider UUID.

    Returns:
        None

    """
    source = get_source(source_id, f'Source ID {source_id} does not exist.')
    if source and source.koku_uuid != koku_uuid:
        source.koku_uuid = koku_uuid
        source.save()


def is_known_source(source_id):
    """
    Check if source exists in database.

    Args:
        source_id (Integer) - Platform-Sources identifier

    Returns:
        source_exists (Boolean) - True if source is known

    """
    try:
        Sources.objects.get(source_id=source_id)
        source_exists = True
    except Sources.DoesNotExist:
        source_exists = False
    return source_exists
