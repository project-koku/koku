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
import copy
import logging
from base64 import b64decode
from json import loads as json_loads
from json.decoder import JSONDecodeError

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
    if provider.billing_source and provider.authentication:
        return True
    return False


def _aws_provider_ready_for_create(provider):
    """Determine if AWS provider is ready for provider creation."""
    if (
        provider.source_id
        and provider.name
        and provider.auth_header
        and aws_settings_ready(provider)
        and not provider.status
        and not provider.koku_uuid
    ):
        return True
    return False


def ocp_settings_ready(provider):
    """Verify that the Application Settings are complete."""
    if provider.authentication:
        return True
    return False


def _ocp_provider_ready_for_create(provider):
    """Determine if OCP provider is ready for provider creation."""
    if (
        provider.source_id
        and provider.name
        and ocp_settings_ready(provider)
        and provider.auth_header
        and not provider.status
        and not provider.koku_uuid
    ):
        return True
    return False


def azure_settings_ready(provider):
    """Verify that the Application Settings are complete."""
    billing_source = provider.billing_source.get("data_source", {})
    authentication = provider.authentication.get("credentials", {})
    if billing_source and authentication:
        if (
            set(authentication.keys()) == REQUIRED_AZURE_AUTH_KEYS
            and set(billing_source.keys()) == REQUIRED_AZURE_BILLING_KEYS
        ):
            return True
    return False


def _azure_provider_ready_for_create(provider):
    """Determine if AZURE provider is ready for provider creation."""
    if (
        provider.source_id
        and provider.name
        and provider.auth_header
        and azure_settings_ready(provider)
        and not provider.status
        and not provider.koku_uuid
    ):
        return True
    return False


def gcp_settings_ready(provider):
    """Verify that the Application Settings are complete."""
    if provider.billing_source.get("data_source") and provider.authentication.get("credentials"):
        return True
    return False


def _gcp_provider_ready_for_create(provider):
    """Determine if GCP provider is ready for provider creation."""
    if (
        provider.source_id
        and provider.name
        and provider.auth_header
        and gcp_settings_ready(provider)
        and not provider.status
        and not provider.koku_uuid
    ):
        return True
    return False


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
    return screen_fn(provider)


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
    providers = Sources.objects.filter(pending_update=True, pending_delete=False, koku_uuid__isnull=False).all()
    for provider in providers:
        providers_to_update.append({"operation": "update", "provider": provider})

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
            providers_to_delete.append({"operation": "destroy", "provider": provider, "offset": provider.offset})
    return providers_to_delete


def get_source(source_id, err_msg, logger):
    """Access Sources, log err on DoesNotExist, close connection on InterfaceError."""
    try:
        return Sources.objects.get(source_id=source_id)
    except Sources.DoesNotExist:
        logger(err_msg)
    except (InterfaceError, OperationalError) as error:
        LOG.error(f"Accessing sources resulted in {type(error).__name__}: {error}")
        raise error


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
            source.save()
    except Sources.DoesNotExist:
        if allow_out_of_order:
            LOG.info(f"Source ID: {source_id} not known.  Marking as out of order delete.")
            new_event = Sources(source_id=source_id, offset=offset, out_of_order_delete=True)
            new_event.save()
            LOG.info(f"source.storage.create_source_event created Source ID as pending delete: {source_id}")
    except (InterfaceError, OperationalError) as error:
        LOG.error(f"Accessing sources resulted in {type(error).__name__}: {error}")
        raise error


def enqueue_source_update(source_id):
    """
    Queues a source update event to be processed by the synchronize_sources method.

    Args:
        source_id (Integer) - Platform-Sources identifier.

    Returns:
        None

    """
    source = get_source(source_id, f"Unable to enqueue source update. Source ID {source_id} not found.", LOG.error)
    if source and source.koku_uuid and not source.pending_delete and not source.pending_update:
        source.pending_update = True
        source.save(update_fields=["pending_update"])


def clear_update_flag(source_id):
    """
    Clear pending update flag after successfully updating Koku provider.

    Args:
        source_id (Integer) - Platform-Sources identifier.

    Returns:
        None

    """
    source = get_source(source_id, f"Unable to clear update flag. Source ID {source_id} not found.", LOG.error)
    if source and source.koku_uuid and source.pending_update:
        source.pending_update = False
        source.save()


def get_source_instance(source_id):
    return get_source(source_id, "Source not found", LOG.info)


def create_source_event(source_id, auth_header, offset):
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
        account_id = json_rh_auth.get("identity", {}).get("account_number")
    except (binascii.Error, JSONDecodeError) as error:
        LOG.error(str(error))
        return

    try:
        source = Sources.objects.filter(source_id=source_id).first()
        if source:
            LOG.debug(f"Source ID {str(source_id)} already exists.")
            if source.out_of_order_delete:
                LOG.info(f"Source ID: {source_id} destroy event already occurred.")
                source.delete()
        else:
            new_event = Sources(source_id=source_id, auth_header=auth_header, offset=offset, account_id=account_id)
            new_event.save()
            LOG.info(f"source.storage.create_source_event created Source ID: {source_id}")
    except (InterfaceError, OperationalError) as error:
        LOG.error(f"source.storage.create_provider_event {type(error).__name__}: {error}")
        raise error


def destroy_source_event(source_id):
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
        LOG.info(f"source.storage.destroy_source_event destroyed Source ID: {source_id}")
    except Sources.DoesNotExist:
        LOG.debug("Source ID: %s already removed.", str(source_id))
    except (InterfaceError, OperationalError) as error:
        LOG.error(f"source.storage.destroy_provider_event {type(error).__name__}: {error}")
        raise error

    return koku_uuid


def get_source_type(source_id):
    """Get Source Type from Source ID."""
    source_type = None
    source = get_source(
        source_id, f"[get_source_type] Unable to get Source Type.  Source ID: {source_id} does not exist", LOG.error
    )
    if source:
        source_type = source.source_type
    return source_type


def add_provider_sources_auth_info(source_id, authentication):
    """
    Add additional Sources information to a Source database object.

    Args:
        source_id (Integer) - Platform-Sources identifier
        authentication (String) - OCP: Sources UID, AWS: RoleARN, etc.

    Returns:
        None

    """
    source = get_source(
        source_id, f"Unable to add authentication details.  Source ID: {source_id} does not exist", LOG.error
    )
    if source:
        current_auth_dict = source.authentication
        subscription_id = None
        if source.source_type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
            if current_auth_dict.get("credentials", {}):
                subscription_id = current_auth_dict.get("credentials", {}).get("subscription_id")
            if subscription_id and authentication.get("credentials"):
                authentication["credentials"]["subscription_id"] = subscription_id
        if source.authentication != authentication:
            source.authentication = authentication
            source.save()


def add_provider_sources_network_info(details, source_id):
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
    source = get_source(source_id, f"Unable to add network details.  Source ID: {source_id} does not exist", LOG.error)
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
        if save_needed:
            source.save()


def add_provider_koku_uuid(source_id, koku_uuid):
    """
    Add Koku provider UUID to Sources database object.

    Args:
        source_id (Integer) - Platform-Sources identifier
        koku_uuid (String) - Koku Provider UUID.

    Returns:
        None

    """
    source = get_source(source_id, f"Source ID {source_id} does not exist.", LOG.error)
    if source and source.koku_uuid != koku_uuid:
        source.koku_uuid = koku_uuid
        source.save()


def save_status(source_id, status):
    """
    Save source status.

    Args:
        source_id (Integer) - Platform-Sources identifier

    Returns:
        status (dict) - source status json

    """
    source = get_source(source_id, f"Source ID {source_id} does not exist.", LOG.warning)
    if source and source.status != status:
        source.status = status
        source.save()
        return True

    return False


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
    except (InterfaceError, OperationalError) as error:
        LOG.error(f"Accessing Sources resulting in {type(error).__name__}: {error}")
        raise error
    return source_exists


def _validate_billing_source(provider_type, billing_source):  # noqa: C901
    """Validate billing source parameters."""
    if provider_type == Provider.PROVIDER_AWS:
        # TODO: Remove `and not billing_source.get("bucket")` if UI is updated to send "data_source" field
        if not billing_source.get("data_source", {}).get("bucket") and not billing_source.get("bucket"):
            raise SourcesStorageError("Missing AWS bucket.")
    elif provider_type == Provider.PROVIDER_AZURE:
        data_source = billing_source.get("data_source")
        if not data_source:
            raise SourcesStorageError("Missing AZURE data_source.")
        if not data_source.get("resource_group"):
            raise SourcesStorageError("Missing AZURE resource_group")
        if not data_source.get("storage_account"):
            raise SourcesStorageError("Missing AZURE storage_account")
    elif provider_type == Provider.PROVIDER_GCP:
        data_source = billing_source.get("data_source")
        if not data_source:
            raise SourcesStorageError("Missing GCP data_source.")
        if not data_source.get("dataset"):
            raise SourcesStorageError("Missing GCP dataset")


def _update_billing_source(instance, billing_source):
    if instance.source_type not in ALLOWED_BILLING_SOURCE_PROVIDERS:
        raise SourcesStorageError(f"Option not supported by source type {instance.source_type}.")
    if instance.billing_source.get("data_source"):
        billing_copy = copy.deepcopy(instance.billing_source.get("data_source"))
        data_source = billing_source.get("data_source", {})
        if data_source.get("resource_group") or data_source.get("storage_account"):
            billing_copy.update(billing_source.get("data_source"))
            billing_source["data_source"] = billing_copy
    _validate_billing_source(instance.source_type, billing_source)
    # This if statement can also be removed if UI is updated to send "data_source" field
    if instance.source_type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL) and not billing_source.get(
        "data_source"
    ):
        billing_source = {"data_source": billing_source}
    return billing_source


def _update_authentication(instance, authentication):
    if instance.source_type not in ALLOWED_AUTHENTICATION_PROVIDERS:
        raise SourcesStorageError(f"Option not supported by source type {instance.source_type}.")
    auth_copy = copy.deepcopy(instance.authentication)
    if not auth_copy.get("credentials"):
        auth_copy["credentials"] = {"subscription_id": None}
    subscription_id = authentication.get("credentials", {}).get("subscription_id")
    auth_copy["credentials"]["subscription_id"] = subscription_id
    return auth_copy


def update_application_settings(source_id, settings):
    """Store billing source update."""
    LOG.info(f"Found settings: {str(settings)}")
    billing_source = settings.get("billing_source")
    authentication = settings.get("authentication")
    if billing_source:
        updated_billing_source = None
        instance = get_source(source_id, "Unable to add billing source", LOG.error)
        if instance.billing_source:
            updated_billing_source = _update_billing_source(instance, billing_source)
        if instance.billing_source != updated_billing_source:
            if instance.billing_source:
                # Queue pending provider update if the billing source was previously
                # populated and now has changed.
                instance.pending_update = True
            instance.billing_source = billing_source
            instance.save()

    if authentication:
        updated_authentication = None
        instance = get_source(source_id, "Unable to add authentication", LOG.error)
        if instance.authentication:
            updated_authentication = _update_authentication(instance, authentication)
        if instance.authentication != updated_authentication:
            if instance.authentication:
                # Queue pending provider update if the authentication was previously
                # populated and now has changed.
                instance.pending_update = True
            instance.authentication = authentication
            if updated_authentication:
                instance.authentication = updated_authentication
            instance.save()
