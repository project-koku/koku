#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Interactions with the rbac service."""
import logging
from collections import OrderedDict
from json.decoder import JSONDecodeError

import requests
from prometheus_client import Counter
from requests.exceptions import ConnectionError
from rest_framework import status

from api.query_handler import WILDCARD
from koku.configurator import CONFIGURATOR
from koku.env import ENVIRONMENT

LOG = logging.getLogger(__name__)
RBAC_CONNECTION_ERROR_COUNTER = Counter("rbac_connection_errors", "Number of RBAC ConnectionErros.")
PROTOCOL = "protocol"
HOST = "host"
PORT = "port"
PATH = "path"
RESOURCE_TYPES = OrderedDict(
    [
        ("aws.account", ["read"]),
        ("aws.organizational_unit", ["read"]),
        ("gcp.account", ["read"]),
        ("gcp.project", ["read"]),
        ("azure.subscription_guid", ["read"]),
        ("openshift.cluster", ["read"]),
        ("openshift.node", ["read"]),
        ("openshift.project", ["read"]),
        ("cost_model", ["read", "write"]),
        ("settings", ["read", "write"]),
    ]
)


def _extract_permission_data(permission):
    """Extract resource type and operation from permission."""
    perm_components = permission.split(":")
    if len(perm_components) != 3:
        raise ValueError("Invalid permission definition.")
    res_typ = perm_components[1]
    operation = perm_components[2]
    return (res_typ, operation)


def _extract_resource_definitions(resource_definitions):
    """Extract resource definition information."""
    result = []
    if resource_definitions == []:
        return [WILDCARD]
    for res_def in resource_definitions:
        att_filter = res_def.get("attributeFilter", {})
        operation = att_filter.get("operation")
        value = att_filter.get("value")
        if operation == "equal" and value:
            result.append(value)
        if operation == "in" and value:
            if isinstance(value, str):
                value = value.split(",")
            result.extend(value)
    return result


def _process_acls(acls):
    """Process acls to determine capabilities."""
    access = {}
    for acl in acls:
        permission = acl.get("permission")
        # Support the legacy term "rate" for cost_model permissions
        if "cost-management:rate" in permission:
            permission = permission.replace("rate", "cost_model")
        resource_definitions = acl.get("resourceDefinitions", [])
        try:
            res_typ, operation = _extract_permission_data(permission)
            resources = _extract_resource_definitions(resource_definitions)
            acl_data = {"operation": operation, "resources": resources}
            if access.get(res_typ) is None:
                access[res_typ] = []
            access[res_typ].append(acl_data)
        except ValueError as exc:
            LOG.error("Skipping invalid ACL: %s", exc)
    if access == {}:
        return None
    return access


def _get_operation(access_item, res_type):
    """Get operation and default wildcard to write for now."""
    operation = access_item.get("operation")
    if operation == WILDCARD:
        operations = RESOURCE_TYPES.get(res_type, [])
        if operations:
            operation = operations[-1]
        else:
            LOG.error("Wildcard specified for invalid resource type - %s", res_type)
            raise ValueError(f"Invalid resource type: {res_type}")
    return operation


def _update_access_obj(access, res_access, resource_list):
    """Update access object with access data."""
    for res in resource_list:
        access_items = access.get(res, [])
        # Set OpenShift rbac inheritance cluster->node->project if higher level is restricted
        if res == "openshift.node":
            if not access_items and res_access["openshift.cluster"]["read"] != []:
                access_items = [{"operation": "read", "resources": ["*"]}]
        if res == "openshift.project":
            if not access_items and res_access["openshift.node"]["read"] != []:
                access_items = [{"operation": "read", "resources": ["*"]}]
        for access_item in access_items:
            operation = _get_operation(access_item, res)
            res_list = access_item.get("resources", [])
            if operation == "write" and res_access[res].get("write") is not None:
                res_access[res]["write"] += res_list
                res_access[res]["read"] += res_list
            if operation == "read":
                res_access[res]["read"] += res_list
    return res_access


def _apply_access(access):  # noqa: C901
    """Apply access to managed resources."""
    res_access = {}
    resources = []
    for res_type, operations in RESOURCE_TYPES.items():
        resources.append(res_type)
        for operation in operations:
            curr = res_access.get(res_type, {})
            curr[operation] = []
            res_access[res_type] = curr
    if access is None:
        return res_access

    # process '*' special case
    wildcard_items = access.get(WILDCARD, [])
    for wildcard_item in wildcard_items:
        res_list = wildcard_item.get("resources", [])
        try:
            for res_type in resources:
                operation = _get_operation(wildcard_item, res_type)
                acl = {"operation": operation, "resources": res_list}
                curr_access = access.get(res_type, [])
                curr_access.append(acl)
                access[res_type] = curr_access
        except ValueError:
            pass

    res_access = _update_access_obj(access, res_access, resources)

    # compact down to only '*' if present
    for res_type, operations in RESOURCE_TYPES.items():
        resources.append(res_type)
        for operation in operations:
            curr = res_access.get(res_type, {})
            res_list = curr.get(operation)
            if any(WILDCARD == item for item in res_list):
                curr[operation] = [WILDCARD]
    return res_access


class RbacConnectionError(ConnectionError):
    """Exception for Rbac ConnectionErrors."""


class RbacService:
    """A class to handle interactions with the RBAC service."""

    def __init__(self):
        """Establish RBAC connection information."""
        rbac_conn_info = self._get_rbac_service()
        self.protocol = rbac_conn_info.get(PROTOCOL)
        self.host = rbac_conn_info.get(HOST)
        self.port = rbac_conn_info.get(PORT)
        self.path = rbac_conn_info.get(PATH)
        self.cache_ttl = ENVIRONMENT.int("RBAC_CACHE_TTL", default=30)

    def _get_rbac_service(self):
        """Get RBAC service host and port info from environment."""
        return {
            PROTOCOL: ENVIRONMENT.get_value("RBAC_SERVICE_PROTOCOL", default="http"),
            HOST: CONFIGURATOR.get_endpoint_host("rbac", "service", "localhost"),
            PORT: CONFIGURATOR.get_endpoint_port("rbac", "service", "8111"),
            PATH: ENVIRONMENT.get_value("RBAC_SERVICE_PATH", default="/r/insights/platform/rbac/v1/access/"),
        }

    def _request_user_access(self, url, headers):  # noqa: C901
        """Send request to RBAC service and handle pagination case."""
        access = []
        try:
            response = requests.get(url, headers=headers)
        except ConnectionError as err:
            LOG.warning("Error requesting user access: %s", err)
            RBAC_CONNECTION_ERROR_COUNTER.inc()
            raise RbacConnectionError(err)

        if response.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            msg = ">=500 Response from RBAC"
            LOG.warning(msg)
            RBAC_CONNECTION_ERROR_COUNTER.inc()
            raise RbacConnectionError(msg)

        if response.status_code != status.HTTP_200_OK:
            try:
                error = response.json()
                LOG.warning("Error requesting user access: %s", error)
            except (JSONDecodeError, ValueError) as res_error:
                LOG.warning("Error processing failed, %s, user access: %s", response.status_code, res_error)
            return access

        # check for pagination handling
        try:
            data = response.json()
        except ValueError as res_error:
            LOG.error("Error processing user access: %s", res_error)
            return access

        if not isinstance(data, dict):
            LOG.error("Error processing user access. Unexpected response object: %s", data)
            return access

        next_link = data.get("links", {}).get("next")
        access = data.get("data", [])
        if next_link:
            next_url = f"{self.protocol}://{self.host}:{self.port}{next_link}"
            access += self._request_user_access(next_url, headers)
        return access

    def get_access_for_user(self, user):
        """Obtain access information for user."""
        url = "{}://{}:{}{}?application=cost-management&limit=100".format(
            self.protocol, self.host, self.port, self.path
        )
        headers = {"x-rh-identity": user.identity_header.get("encoded")}
        acls = self._request_user_access(url, headers)
        if isinstance(acls, list) and len(acls) == 0:
            return None

        processed_acls = _process_acls(acls)
        return _apply_access(processed_acls)

    def get_cache_ttl(self):
        """Return the cache time to live value."""
        return self.cache_ttl
