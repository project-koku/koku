#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import json
import logging

from rest_framework.exceptions import ValidationError

from api.provider.models import Provider
from sources import storage
from sources.config import Config
from sources.sources_http_client import SourcesHTTPClient
from sources.sources_http_client import SourcesHTTPClientError


LOG = logging.getLogger(__name__)

KAFKA_APPLICATION_CREATE = "Application.create"
KAFKA_APPLICATION_UPDATE = "Application.update"
KAFKA_APPLICATION_DESTROY = "Application.destroy"
KAFKA_AUTHENTICATION_CREATE = "Authentication.create"
KAFKA_AUTHENTICATION_UPDATE = "Authentication.update"
KAFKA_SOURCE_UPDATE = "Source.update"
KAFKA_SOURCE_DESTROY = "Source.destroy"
KAFKA_HDR_RH_IDENTITY = "x-rh-identity"
KAFKA_HDR_EVENT_TYPE = "event_type"

SOURCES_OCP_SOURCE_NAME = "openshift"
SOURCES_AWS_SOURCE_NAME = "amazon"
SOURCES_AWS_LOCAL_SOURCE_NAME = "amazon-local"
SOURCES_AZURE_SOURCE_NAME = "azure"
SOURCES_AZURE_LOCAL_SOURCE_NAME = "azure-local"
SOURCES_GCP_SOURCE_NAME = "google"
SOURCES_GCP_LOCAL_SOURCE_NAME = "google-local"

SOURCE_PROVIDER_MAP = {
    SOURCES_OCP_SOURCE_NAME: Provider.PROVIDER_OCP,
    SOURCES_AWS_SOURCE_NAME: Provider.PROVIDER_AWS,
    SOURCES_AWS_LOCAL_SOURCE_NAME: Provider.PROVIDER_AWS_LOCAL,
    SOURCES_AZURE_SOURCE_NAME: Provider.PROVIDER_AZURE,
    SOURCES_AZURE_LOCAL_SOURCE_NAME: Provider.PROVIDER_AZURE_LOCAL,
    SOURCES_GCP_SOURCE_NAME: Provider.PROVIDER_GCP,
    SOURCES_GCP_LOCAL_SOURCE_NAME: Provider.PROVIDER_GCP_LOCAL,
}


class SourcesMessageError(ValidationError):
    """Sources Message error."""


class SourceDetails:
    """Sources Details object."""

    def __init__(self, auth_header, source_id):
        sources_network = SourcesHTTPClient(auth_header, source_id)
        details = sources_network.get_source_details()
        self.name = details.get("name")
        self.source_type_id = int(details.get("source_type_id"))
        self.source_uuid = details.get("uid")
        self.source_type_name = sources_network.get_source_type_name(self.source_type_id)
        self.source_type = SOURCE_PROVIDER_MAP.get(self.source_type_name)


class KafkaMessageProcessor:
    """Base Kafka Message Processor class"""

    def __init__(self, msg, event_type, cost_mgmt_id):
        try:
            self.value = json.loads(msg.value().decode("utf-8"))
            LOG.debug(f"EVENT TYPE: {event_type} | MESSAGE VALUE: {str(self.value)}")
        except (AttributeError, ValueError, TypeError) as error:
            msg = f"[KafkaMessageProcessor] unable to load message: {msg.value}. Error: {error}"
            LOG.error(msg)
            raise SourcesMessageError(msg)
        self.event_type = event_type
        self.cost_mgmt_id = cost_mgmt_id
        self.offset = msg.offset()
        self.partition = msg.partition()
        self.auth_header = extract_from_header(msg.headers(), KAFKA_HDR_RH_IDENTITY)
        if self.auth_header is None:
            msg = f"[KafkaMessageProcessor] missing `{KAFKA_HDR_RH_IDENTITY}`: {msg.headers()}"
            LOG.warning(msg)
            raise SourcesMessageError(msg)
        self.source_id = None

    def __repr__(self):
        return (
            f"{{event_type: {self.event_type}, source_id: {self.source_id},"
            f" partition: {self.partition}, offset: {self.offset}}}"
        )

    def msg_for_cost_mgmt(self):
        """Filter messages not intended for cost management."""
        if self.event_type in (KAFKA_APPLICATION_DESTROY, KAFKA_SOURCE_DESTROY):
            return True
        if self.event_type in (
            KAFKA_APPLICATION_CREATE,
            KAFKA_AUTHENTICATION_CREATE,
            KAFKA_APPLICATION_UPDATE,
            KAFKA_AUTHENTICATION_UPDATE,
        ):
            sources_network = self.get_sources_client()
            return sources_network.get_application_type_is_cost_management(self.cost_mgmt_id)
        return False

    def get_sources_client(self):
        return SourcesHTTPClient(self.auth_header, self.source_id)

    def get_source_details(self):
        return SourceDetails(self.auth_header, self.source_id)

    def save_sources_details(self):
        """
        Get additional sources context from Sources REST API.
        Additional details retrieved from the network includes:
            - Source Name
            - Source Type
            - Source UID
        Details are stored in the Sources database table.
        """
        LOG.info(f"[save_sources_details] starting for source_id {self.source_id} ...")
        details = self.get_source_details()
        if not details.source_type:
            LOG.warning(f"[save_sources_details] unexpected source_type_id: {details.source_type_id}")
            return
        result = storage.add_provider_sources_details(details, self.source_id) or False
        LOG.info(f"[save_sources_details] complete for source_id {self.source_id}: {result}")
        return result

    def save_credentials(self):
        """Store Sources Authentication information."""
        LOG.info(f"[save_credentials] starting for source_id {self.source_id} ...")
        source_type = storage.get_source_type(self.source_id)

        if not source_type:
            LOG.info(f"[save_credentials] source_type not found for source_id: {self.source_id}")
            return

        sources_network = self.get_sources_client()

        try:
            authentication = {"credentials": sources_network.get_credentials(source_type)}
        except SourcesHTTPClientError as error:
            LOG.info(f"[save_credentials] authentication info not available for source_id: {self.source_id}")
            sources_network.set_source_status(error)
            raise error
        else:
            if not authentication.get("credentials"):  # TODO: is this check needed?
                return
            result = bool(storage.add_provider_sources_auth_info(self.source_id, authentication))
            LOG.info(f"[save_credentials] complete for source_id: {self.source_id}: {result}")
            return result

    def save_billing_source(self):
        """Store Sources billing information."""
        LOG.info(f"[save_billing_source] starting for source_id {self.source_id} ...")
        source_type = storage.get_source_type(self.source_id)

        if not source_type:
            LOG.info(f"[save_billing_source] source_type not found for source_id: {self.source_id}")
            return
        if source_type == Provider.PROVIDER_OCP:
            # OCP sources do not have billing sources, so skip running thru this function
            LOG.info("[save_billing_source] skipping for OCP source")
            return

        sources_network = self.get_sources_client()

        try:
            data_source = {"data_source": sources_network.get_data_source(source_type)}
        except SourcesHTTPClientError as error:
            LOG.info(f"[save_billing_source] billing info not available for source_id: {self.source_id}")
            sources_network.set_source_status(error)
            raise error
        else:
            if not data_source.get("data_source"):
                return
            result = bool(storage.add_provider_sources_billing_info(self.source_id, data_source))
            LOG.info(f"[save_billing_source] completed for source_id: {self.source_id}: {result}")
            return result

    def save_source_info(self, auth=False, bill=False):
        """Store sources authentication or billing information."""
        auth_result = False
        bill_result = False
        if auth:
            try:
                auth_result = self.save_credentials()
            except SourcesHTTPClientError:
                return
        if bill:
            try:
                bill_result = self.save_billing_source()
            except SourcesHTTPClientError:
                return

        return auth_result or bill_result


class ApplicationMsgProcessor(KafkaMessageProcessor):
    """Processor for Application events."""

    def __init__(self, msg, event_type, cost_mgmt_id):
        """Constructor for ApplicationMsgProcessor."""
        super().__init__(msg, event_type, cost_mgmt_id)
        self.source_id = int(self.value.get("source_id"))

    def process(self):
        """Process the message."""
        if self.event_type in (KAFKA_APPLICATION_CREATE,):
            storage.create_source_event(self.source_id, self.auth_header, self.offset)

        if storage.is_known_source(self.source_id):
            if self.event_type in (KAFKA_APPLICATION_CREATE,):
                self.save_sources_details()
                self.save_source_info(bill=True)
                # _Authentication_ messages are responsible for saving credentials.
                # However, OCP does not send an Auth message. Therefore, we need
                # to run the following branch for OCP which completes the source
                # creation cycle for an OCP source.
                if storage.get_source_type(self.source_id) == Provider.PROVIDER_OCP:
                    self.save_source_info(auth=True)
            if self.event_type in (KAFKA_APPLICATION_UPDATE,):
                if storage.get_source_type(self.source_id) == Provider.PROVIDER_AZURE:
                    # Because azure auth is split in Sources backend, we need to check both
                    # auth and billing when we recieve either auth update or app update event
                    updated = self.save_source_info(auth=True, bill=True)
                else:
                    updated = self.save_source_info(bill=True)
                if updated:
                    LOG.info(f"[ApplicationMsgProcessor] source_id {self.source_id} updated")
                    storage.enqueue_source_create_or_update(self.source_id)
                else:
                    LOG.info(f"[ApplicationMsgProcessor] source_id {self.source_id} not updated. No changes detected.")

        if self.event_type in (KAFKA_APPLICATION_DESTROY,):
            storage.enqueue_source_delete(self.source_id, self.offset, allow_out_of_order=True)


class AuthenticationMsgProcessor(KafkaMessageProcessor):
    """Processor for Authentication events."""

    def __init__(self, msg, event_type, cost_mgmt_id):
        """Constructor for AuthenticationMsgProcessor."""
        super().__init__(msg, event_type, cost_mgmt_id)
        self.source_id = int(self.value.get("source_id"))

    def process(self):
        """Process the message."""
        if self.event_type in (KAFKA_AUTHENTICATION_CREATE):
            storage.create_source_event(self.source_id, self.auth_header, self.offset)

        if storage.is_known_source(self.source_id):
            if self.event_type in (KAFKA_AUTHENTICATION_CREATE):
                self.save_source_info(auth=True)
            if self.event_type in (KAFKA_AUTHENTICATION_UPDATE):
                if storage.get_source_type(self.source_id) == Provider.PROVIDER_AZURE:
                    # Because azure auth is split in Sources backend, we need to check both
                    # auth and billing when we recieve either auth update or app update event
                    updated = self.save_source_info(auth=True, bill=True)
                else:
                    updated = self.save_source_info(auth=True)
                if updated:
                    LOG.info(f"[AuthenticationMsgProcessor] source_id {self.source_id} updated")
                    storage.enqueue_source_create_or_update(self.source_id)
                else:
                    LOG.info(
                        f"[AuthenticationMsgProcessor] source_id {self.source_id} not updated. No changes detected."
                    )


class SourceMsgProcessor(KafkaMessageProcessor):
    """Processor for Source events."""

    def __init__(self, msg, event_type, cost_mgmt_id):
        """Constructor for SourceMsgProcessor."""
        super().__init__(msg, event_type, cost_mgmt_id)
        self.source_id = int(self.value.get("id"))

    def process(self):
        """Process the message."""
        # if self.event_type in (KAFKA_SOURCE_UPDATE,):  # TODO source.update events are currently ignored
        #     if not storage.is_known_source(self.source_id):
        #         LOG.info("[SourceMsgProcessor] update event for unknown source_id, skipping...")
        #         return
        #     updated = self.save_sources_details()
        #     if updated:
        #         LOG.info(f"[SourceMsgProcessor] source_id {self.source_id} updated")
        #         storage.enqueue_source_create_or_update(self.source_id)
        #     else:
        #         LOG.info(f"[SourceMsgProcessor] source_id {self.source_id} not updated. No changes detected.")

        # elif self.event_type in (KAFKA_SOURCE_DESTROY,):
        if self.event_type in (KAFKA_SOURCE_DESTROY,):
            storage.enqueue_source_delete(self.source_id, self.offset)


def extract_from_header(headers, header_type):
    """Retrieve information from Kafka Headers."""
    if headers is None:
        return "unknown"
    for header in headers:
        if header_type in header:
            for item in header:
                if item == header_type:
                    continue
                else:
                    return item.decode("ascii")
    return None


def create_msg_processor(msg, cost_mgmt_id):
    """Create the message processor based on the event_type."""
    if msg.topic() == Config.SOURCES_TOPIC:
        event_type = extract_from_header(msg.headers(), KAFKA_HDR_EVENT_TYPE)
        LOG.debug(f"event_type: {str(event_type)}")
        if event_type in (KAFKA_APPLICATION_CREATE, KAFKA_APPLICATION_UPDATE, KAFKA_APPLICATION_DESTROY):
            return ApplicationMsgProcessor(msg, event_type, cost_mgmt_id)
        elif event_type in (KAFKA_AUTHENTICATION_CREATE, KAFKA_AUTHENTICATION_UPDATE):
            return AuthenticationMsgProcessor(msg, event_type, cost_mgmt_id)
        elif event_type in (KAFKA_SOURCE_DESTROY,):  # KAFKA_SOURCE_UPDATE):
            return SourceMsgProcessor(msg, event_type, cost_mgmt_id)
        else:
            LOG.debug(f"Other Message: {msg.value()}")
