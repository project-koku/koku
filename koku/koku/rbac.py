#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Interactions with the rbac service."""
import logging
from collections import OrderedDict
from json.decoder import JSONDecodeError
from threading import Lock

import requests
from cachetools import TTLCache
from django.conf import settings
from prometheus_client import Counter
from requests.exceptions import ConnectionError
from rest_framework import status

from api.query_handler import WILDCARD
from koku.configurator import CONFIGURATOR
from koku.env import ENVIRONMENT

LOG = logging.getLogger(__name__)
RBAC_CONNECTION_ERROR_COUNTER = Counter("rbac_connection_errors", "Number of RBAC ConnectionErros.")
_RESOURCE_TYPE_LIST = [
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
if settings.ONPREM:
    _RESOURCE_TYPE_LIST.append(("sources", ["read", "write"]))
RESOURCE_TYPES = OrderedDict(_RESOURCE_TYPE_LIST)
# Only these applications contribute to koku's access map. Other apps may also
# use `app:*:*`, which must not be treated as a Cost-wide wildcard.
_COST_APPLICATIONS = ("cost-management",) + (("sources",) if settings.ONPREM else ())


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


def _normalize_sources_acls(acls):
    """Collapse "sources" application permissions onto the koku `sources` resource type.

    RBAC returns sources permissions as ``sources:<resource>:<operation>`` -- e.g.
    ``sources:*:*`` for the "Sources administrator" role. On-prem, RESOURCE_TYPES
    has a single flat ``sources`` entry, and ``_extract_permission_data`` keys off
    the middle segment, so ``sources:*:*`` would otherwise land under the ``*``
    wildcard and get expanded across every resource type. Rewrite the middle
    segment to ``sources`` so the permission maps to that single bucket.
    """
    normalized = []
    for acl in acls:
        acl = dict(acl)
        parts = acl.get("permission", "").split(":")
        if len(parts) == 3 and parts[0] == "sources":
            acl["permission"] = f"sources:sources:{parts[2]}"
        normalized.append(acl)
    return normalized


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
        self.base_url = CONFIGURATOR.get_endpoint_url("rbac", "service", "http://localhost:8111")
        self.path = ENVIRONMENT.get_value("RBAC_SERVICE_PATH", default="/r/insights/platform/rbac/v1/access/")
        self.cache_ttl = ENVIRONMENT.int("RBAC_CACHE_TTL", default=30)

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
            next_url = f"{self.base_url}{next_link}"
            access += self._request_user_access(next_url, headers)
        return access

    def get_access_for_user(self, user):
        """Obtain access information for user."""
        base_url = f"{self.base_url}{self.path}"
        headers = {"x-rh-identity": user.identity_header.get("encoded")}
        acls = self._request_user_access(f"{base_url}?application=cost-management&limit=100", headers)

        if settings.ONPREM:
            # The "Sources administrator" role (sources:*:*) lives in the "sources"
            # RBAC application, which the cost-management filter above excludes.
            # Fetch it separately so the user-access API can report a `sources`
            # capability that gates the on-prem Settings > Integrations tab.
            try:
                sources_acls = self._request_user_access(f"{base_url}?application=sources&limit=100", headers)
            except RbacConnectionError:
                LOG.warning("Sources ACL lookup failed; continuing with cost-management access only.")
                sources_acls = []
            acls = list(acls) + _normalize_sources_acls(sources_acls)

        if isinstance(acls, list) and len(acls) == 0:
            return None

        processed_acls = _process_acls(acls)
        return _apply_access(processed_acls)

    def get_cache_ttl(self):
        """Return the cache time to live value."""
        return self.cache_ttl


# Verbs a v2 role permission may carry. "write" implies read, matching v1.
_WRITE_VERBS = {"write", "edit", "create", "delete", "move"}


def _v2_permission_to_v1(permission):
    """Normalise a V2 permission (dict or string) to the V1 `app:resource:verb` form."""
    if isinstance(permission, str):
        return permission
    if not isinstance(permission, dict):
        return None
    application = permission.get("application")
    resource_type = permission.get("resource_type")
    verb = permission.get("operation") or permission.get("verb")
    if not (application and resource_type and verb):
        return None
    return f"{application}:{resource_type}:{verb}"


class RbacV2Service:
    """Read Cost grants from RBAC v2 role bindings.

    Produces the same ``user.access`` structure as the v1 ``/access/`` call so the
    rest of the API layer (permission classes, ``set_access_filters``) is unchanged.

    In v2 a grant is ``(subject, role, workspace)``; the permissions come from the
    role and the concrete resource ids from the workspace mapping convention
    selected by ``RBAC_V2_RESOURCE_ID_FIELD`` (``name`` for the lab, ``id`` with a
    Cost-side mapping table in production).
    """

    def __init__(self):
        self.protocol = ENVIRONMENT.get_value("RBAC_V2_SERVICE_PROTOCOL", default="http")
        self.host = ENVIRONMENT.get_value("RBAC_V2_SERVICE_HOST", default="localhost")
        self.port = ENVIRONMENT.int("RBAC_V2_SERVICE_PORT", default=8000)
        self.path = ENVIRONMENT.get_value("RBAC_V2_SERVICE_PATH", default="/api/rbac/v2")
        self.timeout = ENVIRONMENT.int("RBAC_V2_TIMEOUT", default=5)
        self.cache_ttl = ENVIRONMENT.int("RBAC_CACHE_TTL", default=30)
        self.role_cache_ttl = ENVIRONMENT.int("RBAC_V2_ROLE_CACHE_TTL", default=300)
        self.service_identity = ENVIRONMENT.get_value("RBAC_V2_SERVICE_IDENTITY", default="")
        self.resource_id_field = ENVIRONMENT.get_value("RBAC_V2_RESOURCE_ID_FIELD", default="id")
        self.shadow = ENVIRONMENT.bool("RBAC_V2_SHADOW", default=False)
        self._role_cache = TTLCache(maxsize=1024, ttl=self.role_cache_ttl)
        self._role_lock = Lock()

    def _base_url(self):
        return f"{self.protocol}://{self.host}:{self.port}{self.path}"

    @staticmethod
    def _principal_id(user):
        decoded = (getattr(user, "identity_header", None) or {}).get("decoded") or {}
        user_block = (decoded.get("identity") or {}).get("user") or {}
        return user_block.get("user_id")

    def _headers(self, user):
        """Prefer the configured service identity: unscoped binding reads are admin-only in v2."""
        if self.service_identity:
            return {"x-rh-identity": self.service_identity}
        identity = (getattr(user, "identity_header", None) or {}).get("encoded")
        return {"x-rh-identity": identity} if identity else {}

    def _request_bindings(self, url, headers):
        """Fetch role bindings, following cursor pagination."""
        bindings = []
        while url:
            try:
                response = requests.get(url, headers=headers, timeout=self.timeout)
            except ConnectionError as err:
                LOG.warning("Error requesting RBAC v2 bindings: %s", err)
                RBAC_CONNECTION_ERROR_COUNTER.inc()
                raise RbacConnectionError(err)

            if response.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
                msg = ">=500 Response from RBAC v2"
                LOG.warning(msg)
                RBAC_CONNECTION_ERROR_COUNTER.inc()
                raise RbacConnectionError(msg)

            if response.status_code != status.HTTP_200_OK:
                LOG.warning("Error requesting RBAC v2 bindings: %s", response.status_code)
                return bindings

            try:
                data = response.json()
            except (JSONDecodeError, ValueError) as res_error:
                LOG.error("Error processing RBAC v2 bindings: %s", res_error)
                return bindings

            bindings.extend(data.get("data", []))

            next_link = (data.get("links") or {}).get("next")
            if next_link:
                if next_link.startswith("http"):
                    url = next_link
                else:
                    url = f"{self.protocol}://{self.host}:{self.port}{next_link}"
            else:
                url = None
        return bindings

    def _role_permissions(self, role_id, headers):
        """Return the V1 permission strings for a role, cached by role id."""
        if not role_id:
            return []
        with self._role_lock:
            cached = self._role_cache.get(role_id)
        if cached is not None:
            return cached

        url = f"{self._base_url()}/roles/{role_id}/"
        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
        except ConnectionError as err:
            LOG.warning("Error requesting RBAC v2 role %s: %s", role_id, err)
            RBAC_CONNECTION_ERROR_COUNTER.inc()
            raise RbacConnectionError(err)

        if response.status_code != status.HTTP_200_OK:
            LOG.warning("Error requesting RBAC v2 role %s: %s", role_id, response.status_code)
            return []

        payload = response.json()
        role = payload.get("data", payload)
        permissions = [p for p in (_v2_permission_to_v1(x) for x in role.get("permissions") or []) if p]

        with self._role_lock:
            self._role_cache[role_id] = permissions
        return permissions

    @staticmethod
    def _target_operations(verb, operations):
        """Return the koku operations a v1-style verb grants for a resource type."""
        if verb == WILDCARD:
            return list(operations)
        if verb in _WRITE_VERBS:
            # v1 semantics: write implies read.
            return [op for op in ("write", "read") if op in operations]
        if verb == "read":
            return ["read"] if "read" in operations else []
        return []

    @staticmethod
    def _add_permission(access, permission, resource_ids):
        try:
            application, resource_type, verb = permission.split(":")
        except ValueError:
            LOG.warning("Skipping malformed RBAC v2 permission: %s", permission)
            return

        if application not in _COST_APPLICATIONS:
            return

        if resource_type == WILDCARD:
            resource_types = list(RESOURCE_TYPES)
        elif resource_type in RESOURCE_TYPES:
            resource_types = [resource_type]
        else:
            LOG.warning("Skipping RBAC v2 permission for unknown resource type: %s", permission)
            return

        for res_type in resource_types:
            operations = RESOURCE_TYPES[res_type]
            targets = RbacV2Service._target_operations(verb, operations)
            if not targets:
                continue
            bucket = access.setdefault(res_type, {op: [] for op in operations})
            for operation in targets:
                bucket.setdefault(operation, []).extend(resource_ids)

    @staticmethod
    def _compact(access):
        for operations in access.values():
            for operation, ids in operations.items():
                if WILDCARD in ids:
                    operations[operation] = [WILDCARD]
                else:
                    operations[operation] = list(dict.fromkeys(ids))
        return access

    def _get_v2_access(self, user, headers):
        params = {
            "granted_subject_type": "principal",
            "granted_subject.principal.user_id": self._principal_id(user),
            "exclude_sources": "none",
            "fields": "role(id,name),resource(id,name)",
            "limit": 100,
        }
        url = f"{self._base_url()}/role-bindings/?" + "&".join(f"{k}={v}" for k, v in params.items())
        bindings = self._request_bindings(url, headers)

        access = _apply_access(None)
        for binding in bindings:
            role = binding.get("role") or {}
            resource = binding.get("resource") or {}
            resource_id = resource.get(self.resource_id_field) or resource.get("id")
            if not resource_id:
                continue
            for permission in self._role_permissions(role.get("id"), headers):
                self._add_permission(access, permission, [str(resource_id)])
        return self._compact(access)

    def get_access_for_user(self, user):
        """Return the user's access in the same shape as the V1 `/access/` response."""
        if not self._principal_id(user):
            LOG.warning("RBAC v2: identity header has no user.user_id; denying access")
            return _apply_access(None)

        headers = self._headers(user)
        if self.shadow:
            v1_access = RbacService().get_access_for_user(user)
            v2_access = self._get_v2_access(user, headers)
            if v1_access != v2_access:
                LOG.warning(
                    "RBAC v2 shadow mismatch: user_id=%s v1=%s v2=%s",
                    self._principal_id(user),
                    v1_access,
                    v2_access,
                )
            return v1_access
        return self._get_v2_access(user, headers)


def get_rbac_service():
    """Return the configured RBAC backend (v1 `/access/`, or v2 role bindings)."""
    if settings.RBAC_BACKEND == "v2":
        return RbacV2Service()
    return RbacService()
