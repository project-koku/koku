#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessors for Sources database table."""
import logging

from django.db import InterfaceError
from django.db import OperationalError

from api.provider.models import Provider
from api.provider.models import Sources


LOG = logging.getLogger(__name__)
REQUIRED_AZURE_AUTH_KEYS = {"client_id", "tenant_id", "client_secret", "subscription_id"}
REQUIRED_AZURE_BILLING_KEYS = {"resource_group", "storage_account"}
ALLOWED_BILLING_SOURCE_PROVIDERS = (
    Provider.PROVIDER_AWS,
    Provider.PROVIDER_AWS_LOCAL,
    Provider.PROVIDER_AZURE,
    Provider.PROVIDER_AZURE_LOCAL,
    Provider.PROVIDER_GCP,
    Provider.PROVIDER_GCP_LOCAL,
)
ALLOWED_AUTHENTICATION_PROVIDERS = (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL)


class SourcesStorageError(Exception):
    """Sources Storage error."""


def aws_settings_ready(provider):
    """Verify that the Application Settings are complete."""
    return bool(provider.billing_source and provider.authentication)


def _aws_provider_ready_for_create(provider):
    """Determine if AWS provider is ready for provider creation."""
    return bool(
        provider.source_id
        and provider.name
        and provider.auth_header
        and aws_settings_ready(provider)
        and not provider.status
        and not provider.koku_uuid
    )


def ocp_settings_ready(provider):
    """Verify that the Application Settings are complete."""
    return bool(provider.authentication)


def _ocp_provider_ready_for_create(provider):
    """Determine if OCP provider is ready for provider creation."""
    return bool(
        provider.source_id
        and provider.name
        and ocp_settings_ready(provider)
        and provider.auth_header
        and not provider.status
        and not provider.koku_uuid
    )


def azure_settings_ready(provider):
    """Verify that the Application Settings are complete."""
    billing_source = provider.billing_source.get("data_source", {})
    authentication = provider.authentication.get("credentials", {})
    return bool(
        billing_source
        and authentication
        and (
            set(authentication.keys()) == REQUIRED_AZURE_AUTH_KEYS
            and REQUIRED_AZURE_BILLING_KEYS.issubset(set(billing_source.keys()))
        )
    )


def _azure_provider_ready_for_create(provider):
    """Determine if AZURE provider is ready for provider creation."""
    return bool(
        provider.source_id
        and provider.name
        and provider.auth_header
        and azure_settings_ready(provider)
        and not provider.status
        and not provider.koku_uuid
    )


def gcp_settings_ready(provider):
    """Verify that the Application Settings are complete."""
    return bool(provider.billing_source.get("data_source") and provider.authentication.get("credentials"))


def _gcp_provider_ready_for_create(provider):
    """Determine if GCP provider is ready for provider creation."""
    return bool(
        provider.source_id
        and provider.name
        and provider.auth_header
        and gcp_settings_ready(provider)
        and not provider.status
        and not provider.koku_uuid
    )


SCREEN_MAP = {
    Provider.PROVIDER_AWS: _aws_provider_ready_for_create,
    Provider.PROVIDER_AWS_LOCAL: _aws_provider_ready_for_create,
    Provider.PROVIDER_OCP: _ocp_provider_ready_for_create,
    Provider.PROVIDER_AZURE: _azure_provider_ready_for_create,
    Provider.PROVIDER_AZURE_LOCAL: _azure_provider_ready_for_create,
    Provider.PROVIDER_GCP: _gcp_provider_ready_for_create,
    Provider.PROVIDER_GCP_LOCAL: _gcp_provider_ready_for_create,
}


def screen_and_build_provider_sync_create_event(provider):
    """Determine if the source should be queued for synchronization."""
    provider_event = {}
    screen_fn = SCREEN_MAP.get(provider.source_type)
    if screen_fn and screen_fn(provider) and not provider.pending_delete:
        provider_event = {"operation": "create", "provider": provider, "offset": provider.offset}
    return provider_event


APP_SETTINGS_SCREEN_MAP = {
    Provider.PROVIDER_AWS: aws_settings_ready,
    Provider.PROVIDER_AWS_LOCAL: aws_settings_ready,
    Provider.PROVIDER_OCP: ocp_settings_ready,
    Provider.PROVIDER_AZURE: azure_settings_ready,
    Provider.PROVIDER_AZURE_LOCAL: azure_settings_ready,
    Provider.PROVIDER_GCP: gcp_settings_ready,
    Provider.PROVIDER_GCP_LOCAL: gcp_settings_ready,
}


def source_settings_complete(provider):
    """Determine if the source application settings are complete."""
    screen_fn = APP_SETTINGS_SCREEN_MAP.get(provider.source_type)
    return screen_fn(provider) if screen_fn else False


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
    providers = Sources.objects.filter(pending_update=True, pending_delete=False, koku_uuid__isnull=False).all()
    return [{"operation": "update", "provider": provider} for provider in providers]


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
    all_providers = Sources.objects.all()
    return [
        {"operation": "destroy", "provider": provider, "offset": provider.offset}
        for provider in all_providers
        if provider.pending_delete
    ]


def get_source(source_id, err_msg, logger) -> Sources:
    """Access Sources, log err on DoesNotExist, close connection on InterfaceError."""
    try:
        return Sources.objects.get(source_id=source_id)
    except Sources.DoesNotExist:
        logger(err_msg)
    except (InterfaceError, OperationalError) as error:
        LOG.error(f"Accessing sources resulted in {type(error).__name__}: {error}")
        raise error


def mark_provider_as_inactive(provider_uuid):
    """Mark provider as inactive so we do not continue to ingest data while the source is being deleted."""
    try:
        provider = Provider.objects.get(uuid=provider_uuid)
        provider.active = False
        provider.billing_source = None
        provider.authentication = None
        provider.save()
    except Provider.DoesNotExist:
        LOG.info(f"Provider {provider_uuid} does not exist.  Unable to mark as inactive")


def enqueue_source_delete(source_id, offset, allow_out_of_order=False):
    """
    Queues a source destroy event to be processed by the synchronize_sources method.

    Args:
        queue (Asyncio Queue) - process_queue containing all pending Souces-koku events.
        source_id (Integer) - Platform-Sources identifier.
        allow_out_of_order (Bool) - Allow for out of order delete events (Application or Source).

    Returns:
        None

    """
    try:
        source = Sources.objects.get(source_id=source_id)
        if not source.pending_delete and not source.out_of_order_delete:
            source.pending_delete = True
            LOG.info(f"[enqueue_source_delete] source_id: {source_id} marked for deletion")
            source.save()
    except Sources.DoesNotExist:
        if allow_out_of_order:
            LOG.info(f"[enqueue_source_delete] source_id: {source_id} not known. Marking as out of order delete.")
            new_event = Sources(source_id=source_id, offset=offset, out_of_order_delete=True)
            new_event.save()
            LOG.info(f"[enqueue_source_delete] created source_id as pending delete: {source_id}")
        else:
            LOG.info(f"[enqueue_source_delete] source_id: {source_id} already removed")
    except (InterfaceError, OperationalError) as error:
        LOG.error(f"Accessing sources resulted in {type(error).__name__}: {error}")
        raise error


def enqueue_source_create_or_update(source_id):
    """
    Queues a source update event to be processed by the synchronize_sources method.

    Args:
        source_id (Integer) - Platform-Sources identifier.

    Returns:
        None

    """
    source = get_source(
        source_id, f"[enqueue_source_create_or_update] error: source_id: {source_id} does not exist.", LOG.error
    )
    if source and not source.pending_delete and not source.pending_update:
        if not source.koku_uuid:
            source.status = None
        else:
            source.pending_update = True
        source.save()


def clear_update_flag(source_id):
    """Clear pending update flag after updating Koku provider."""
    source = get_source(source_id, f"[clear_update_flag] error: source_id: {source_id} does not exist.", LOG.error)
    if source and source.koku_uuid and source.pending_update:
        source.pending_update = False
        source.save()


def get_source_instance(source_id):
    return get_source(source_id, f"[get_source_instance] source_id: {source_id} does not exist.", LOG.info)


def create_source_event(source_id, account_id, org_id, auth_header, offset):
    """Create a Sources database object."""
    LOG.info(f"[create_source_event] starting for source_id {source_id} ...")
    try:
        source = Sources.objects.filter(source_id=source_id).first()
        if source:
            LOG.info(f"[create_source_event] source_id: {str(source_id)} already exists.")
            if source.out_of_order_delete:
                LOG.info(f"[create_source_event] source_id: {source_id} destroy event already occurred.")
                source.delete()
        else:
            new_event = Sources(
                source_id=source_id, auth_header=auth_header, offset=offset, account_id=account_id, org_id=org_id
            )
            new_event.save()
            LOG.info(f"[create_source_event] created source_id: {source_id}")
    except (InterfaceError, OperationalError) as error:
        LOG.error(f"[create_source_event] {type(error).__name__}: {error}")
        raise error


def destroy_source_event(source_id):
    """Destroy a Sources database object."""
    LOG.info("destroy source event...")
    koku_uuid = None
    try:
        source = Sources.objects.get(source_id=source_id)
        koku_uuid = source.koku_uuid
        source.delete()
        LOG.info(f"[destroy_source_event] destroyed source_id: {source_id}")
    except Sources.DoesNotExist:
        LOG.debug(f"[destroy_source_event] source_id: {source_id} already removed.")
    except (InterfaceError, OperationalError) as error:
        LOG.error(f"[destroy_source_event] {type(error).__name__}: {error}")
        raise error
    return koku_uuid


def get_source_type(source_id):
    """Get Source Type from source_id."""
    source_type = None
    source = get_source(source_id, f"[get_source_type] error: source_id: {source_id} does not exist", LOG.error)
    if source:
        source_type = source.source_type
    return source_type


def add_provider_sources_auth_info(source_id, authentication):
    """Add additional Sources information to a Source database object."""
    source = get_source(
        source_id, f"[add_provider_sources_auth_info] error: source_id: {source_id} does not exist", LOG.error
    )
    if source and source.authentication != authentication:
        source.authentication = authentication
        source.save()
        return True


def add_provider_sources_billing_info(source_id, billing_source):
    """Add additional Sources information to a Source database object."""
    source = get_source(
        source_id, f"[add_provider_sources_billing_info] error: source_id: {source_id} does not exist", LOG.error
    )
    if source and source.billing_source != billing_source:
        source.billing_source = billing_source
        source.save()
        return True


def add_provider_sources_details(details, source_id):
    """Add additional Sources information to a Source database object."""
    save_needed = False
    source = get_source(
        source_id, f"[add_provider_sources_details] error: source_id: {source_id} does not exist", LOG.error
    )
    if source:
        if source.name != details.name:
            source.name = details.name
            save_needed = True
        if str(source.source_uuid) != details.source_uuid:
            source.source_uuid = details.source_uuid
            save_needed = True
        if source.source_type != details.source_type:
            source.source_type = details.source_type
            save_needed = True
        if source.auth_header != details.auth_header:
            source.auth_header = details.auth_header
            save_needed = True
        if save_needed:
            source.save()
            return True


def add_provider_koku_uuid(source_id, koku_uuid):
    """Add Koku provider UUID to Sources database object."""
    LOG.info(f"[add_provider_koku_uuid] start attaching koku_uuid: {koku_uuid} to source_id: {source_id}")
    source = get_source(
        source_id, f"[add_provider_koku_uuid] error: source_id: {source_id} does not exist.", LOG.error
    )
    if source and source.koku_uuid != koku_uuid:
        LOG.info(f"[add_provider_koku_uuid] attached koku_uuid: {koku_uuid} to source_id: {source_id}")
        source_query = Sources.objects.filter(source_id=source.source_id)
        source_query.update(koku_uuid=koku_uuid, provider_id=koku_uuid)


def add_source_pause(source_id, pause):
    """Add pause to Sources database object."""
    LOG.info(f"[add_source_pause] start setting pause: {pause} to source_id: {source_id}")
    source = get_source(source_id, f"[add_source_pause] error: source_id: {source_id} does not exist.", LOG.error)
    if source and source.paused != pause:
        LOG.info(f"[add_source_pause] set pause: {pause} on source_id: {source_id}")
        source.paused = pause
        source.pending_update = True
        source.save()


def save_status(source_id, status):
    """Save source status."""
    source = get_source(source_id, f"[save_status] warning: source_id: {source_id} does not exist.", LOG.warning)
    if source and source.status != status:
        source.status = status
        source.save()
        return True

    return False


def is_known_source(source_id):
    """Check if source exists in database."""
    LOG.debug(f"[is_known_source] checking if source_id: {source_id} is known.")
    try:
        Sources.objects.get(source_id=source_id)
        source_exists = True
    except Sources.DoesNotExist:
        source_exists = False
    except (InterfaceError, OperationalError) as error:
        LOG.error(f"Accessing Sources resulting in {type(error).__name__}: {error}")
        raise error
    LOG.debug(f"[is_known_source] source_id: {source_id} is known: {source_exists}")
    return source_exists
