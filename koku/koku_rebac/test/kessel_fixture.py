#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Kessel E2E fixture helper -- seeds and cleans up SpiceDB tuples via Relations API REST.

Translates RBAC-style access dicts (e.g. ``{"aws.account": {"read": ["*"]}}``)
into the full Kessel tuple chain:

    rbac/role  -> rbac/role_binding -> rbac/workspace
                                   -> rbac/principal

Usage in tests::

    from koku_rebac.test.kessel_fixture import KesselFixture

    fixture = KesselFixture()
    fixture.seed_access("org123", "testuser", {"aws.account": {"read": ["*"]}})
    # ... run tests ...
    fixture.cleanup()
"""
import logging
import os
import time
import uuid

import requests

LOG = logging.getLogger(__name__)

RELATIONS_API_URL = os.environ.get("KESSEL_RELATIONS_URL", "http://localhost:8100")
TUPLES_PATH = os.environ.get("KESSEL_TUPLES_PATH", "/api/authz/v1beta1/tuples")
CHECK_PATH = "/api/authz/v1beta1/check"
CONSISTENCY_TIMEOUT = float(os.environ.get("KESSEL_CONSISTENCY_TIMEOUT", "30"))

KOKU_TO_KESSEL_TYPE_MAP: dict[str, str] = {
    "aws.account": "aws_account",
    "aws.organizational_unit": "aws_organizational_unit",
    "gcp.account": "gcp_account",
    "gcp.project": "gcp_project",
    "azure.subscription_guid": "azure_subscription_guid",
    "openshift.cluster": "openshift_cluster",
    "openshift.node": "openshift_node",
    "openshift.project": "openshift_project",
    "cost_model": "cost_model",
    "settings": "settings",
}

VERB_TO_RELATION_SUFFIX: dict[str, str] = {
    "read": "read",
    "write": "write",
}


def _ref(namespace: str, name: str, obj_id: str) -> dict:
    """Build a Relations API object/subject reference."""
    return {"type": {"namespace": namespace, "name": name}, "id": obj_id}


def _tuple(resource_ns: str, resource_name: str, resource_id: str, relation: str, subject_ns: str, subject_name: str, subject_id: str) -> dict:
    """Build a single Relations API tuple."""
    return {
        "resource": _ref(resource_ns, resource_name, resource_id),
        "relation": relation,
        "subject": {"subject": _ref(subject_ns, subject_name, subject_id)},
    }


def _poll_until(predicate, timeout: float, label: str = "") -> bool:
    """Poll *predicate* with exponential backoff until it returns True or timeout."""
    deadline = time.monotonic() + timeout
    interval = 0.5
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(min(interval, max(0, deadline - time.monotonic())))
        interval = min(interval * 2, 5.0)
    if label:
        LOG.warning("Polling timeout (%.0fs) for %s", timeout, label)
    return False


class KesselFixture:
    """Seeds and cleans up Kessel tuples for E2E tests."""

    def __init__(self, relations_url: str | None = None):
        self._url = (relations_url or RELATIONS_API_URL).rstrip("/")
        self._tuples_url = f"{self._url}{TUPLES_PATH}"
        self._check_url = f"{self._url}{CHECK_PATH}"
        self._created_items: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cleanup()
        return False

    def seed_access(self, workspace_id: str, username: str, access: dict) -> None:
        """Seed the full tuple chain for a user given an RBAC-style access dict.

        For each (resource_type, operation) pair where the value is non-empty
        (e.g. ``["*"]``), creates:

        1. ``rbac/role:<role-id>#t_cost_management_<kessel_type>_<verb> -> rbac/principal:*``
        2. ``rbac/role_binding:<rb-id>#t_granted -> rbac/role:<role-id>``
        3. ``rbac/role_binding:<rb-id>#t_subject -> rbac/principal:redhat/<username>``
        4. ``rbac/workspace:<workspace_id>#t_binding -> rbac/role_binding:<rb-id>``

        After creating tuples, polls the Relations API Check endpoint until
        the first permission is confirmed visible (or timeout expires).
        """
        tuples = self._rbac_to_tuples(workspace_id, username, access)
        if not tuples:
            return
        self._create_tuples(tuples)

        first_kessel_type, first_relation = self._first_permission(access)
        if first_kessel_type and first_relation:
            self._wait_for_consistency(
                workspace_id=workspace_id,
                kessel_type=first_kessel_type,
                relation=first_relation,
                subject_id=f"redhat/{username}",
                expected=True,
            )

    def seed_inventory_resources(
        self,
        workspace_id: str,
        kessel_type: str,
        resource_ids: list[str],
        *,
        wait_user: str | None = None,
        wait_relation: str = "read",
    ) -> None:
        """Seed resource tuples so StreamedListObjects can discover them.

        Creates ``cost_management/<kessel_type>:<id>#t_workspace -> rbac/workspace:<workspace_id>``
        for each resource ID.  Works for any Kessel Inventory resource type.

        If *wait_user* is provided, polls until SpiceDB confirms the first
        resource is visible via a resource-level Check.  *wait_relation*
        controls which permission is checked (default ``read``; use ``write``
        for types where the user only has write access).

        This is necessary because SpiceDB's ``minimize_latency`` consistency
        uses a quantized revision that may not include freshly written tuples.
        """
        tuples = [
            _tuple("cost_management", kessel_type, rid, "t_workspace", "rbac", "workspace", workspace_id)
            for rid in resource_ids
        ]
        if tuples:
            self._create_tuples(tuples)
            for rid in resource_ids:
                self._created_items.append(
                    {"ns": "cost_management", "name": kessel_type, "id": rid, "relation": "t_workspace"}
                )
            if wait_user and resource_ids:
                self._wait_for_resource_visibility(kessel_type, resource_ids[0], wait_user, wait_relation)

    def seed_ocp_resources(
        self, workspace_id: str, kessel_type: str, resource_ids: list[str],
        *, wait_user: str | None = None, wait_relation: str = "read",
    ) -> None:
        """Backward-compatible alias for seed_inventory_resources."""
        self.seed_inventory_resources(workspace_id, kessel_type, resource_ids, wait_user=wait_user, wait_relation=wait_relation)

    def seed_all_read_wildcard(self, workspace_id: str, username: str) -> None:
        """Seed a role with ``t_cost_management_all_read`` for KSL wildcard testing.

        Grants the user read access to ALL cost_management types via the
        app-level wildcard relation.
        """
        tag = uuid.uuid4().hex[:8]
        role_id = f"e2e-role-all-read-{tag}"
        rb_id = f"e2e-rb-all-read-{tag}"
        principal_id = f"redhat/{username}"

        tuples = [
            _tuple("rbac", "role", role_id, "t_cost_management_all_read", "rbac", "principal", "*"),
            _tuple("rbac", "role_binding", rb_id, "t_granted", "rbac", "role", role_id),
            _tuple("rbac", "role_binding", rb_id, "t_subject", "rbac", "principal", principal_id),
            _tuple("rbac", "workspace", workspace_id, "t_binding", "rbac", "role_binding", rb_id),
        ]
        self._create_tuples(tuples)
        self._created_items.extend([
            {"ns": "rbac", "name": "role", "id": role_id, "relation": "t_cost_management_all_read"},
            {"ns": "rbac", "name": "role_binding", "id": rb_id, "relation": "t_granted"},
            {"ns": "rbac", "name": "role_binding", "id": rb_id, "relation": "t_subject"},
        ])

        self._wait_for_consistency(
            workspace_id=workspace_id,
            kessel_type="aws_account",
            relation="cost_management_all_read",
            subject_id=principal_id,
            expected=True,
        )

    def delete_resource_tuples(self, kessel_type: str, resource_id: str) -> None:
        """Delete the resource-to-workspace SpiceDB tuple for a specific resource.

        Removes ``cost_management/<kessel_type>:<resource_id>#t_workspace``
        from SpiceDB via the Relations API.  This is the targeted cleanup
        needed when a resource is decommissioned.
        """
        self._delete_tuples("cost_management", kessel_type, resource_id, "t_workspace")

    def cleanup(self) -> None:
        """Best-effort cleanup of all tuples created by this fixture.

        Removes role bindings, roles, and workspace bindings.  Silently
        ignores errors so test tearDown always completes.
        """
        if not self._created_items:
            return
        for item in self._created_items:
            self._delete_tuples(item["ns"], item["name"], item["id"], item["relation"])
        self._created_items.clear()

    def _first_permission(self, access: dict) -> tuple[str | None, str | None]:
        """Extract the first (kessel_type, relation_name) from an access dict for polling."""
        for koku_type, operations in access.items():
            kessel_type = KOKU_TO_KESSEL_TYPE_MAP.get(koku_type)
            if not kessel_type or not isinstance(operations, dict):
                continue
            for verb, value in operations.items():
                if not value:
                    continue
                relation_suffix = VERB_TO_RELATION_SUFFIX.get(verb)
                if relation_suffix:
                    return kessel_type, f"cost_management_{kessel_type}_{relation_suffix}"
        return None, None

    def _check_relation(self, workspace_id: str, kessel_type: str, relation: str, subject_id: str) -> bool:
        """Send a single Relations API Check and return True if ALLOWED_TRUE."""
        payload = {
            "resource": _ref("rbac", "workspace", workspace_id),
            "relation": relation,
            "subject": {"subject": _ref("rbac", "principal", subject_id)},
        }
        try:
            resp = requests.post(self._check_url, json=payload, timeout=5)
            if resp.ok:
                data = resp.json()
                return data.get("allowed", 0) == 1 or data.get("allowed") == "ALLOWED_TRUE"
        except Exception:
            LOG.debug("Check poll failed", exc_info=True)
        return False

    def _wait_for_consistency(
        self,
        workspace_id: str,
        kessel_type: str,
        relation: str,
        subject_id: str,
        expected: bool = True,
        timeout: float | None = None,
    ) -> None:
        """Poll the Relations API Check endpoint until the expected result or timeout."""
        timeout = timeout or CONSISTENCY_TIMEOUT
        _poll_until(
            predicate=lambda: self._check_relation(workspace_id, kessel_type, relation, subject_id) == expected,
            timeout=timeout,
            label=f"{'ALLOWED' if expected else 'DENIED'} on {kessel_type}/{relation} for {subject_id}",
        )

    def _wait_for_resource_visibility(self, kessel_type: str, resource_id: str, username: str, relation: str = "read") -> None:
        """Poll a resource-level Check until SpiceDB confirms visibility."""
        subject_id = f"redhat/{username}"

        def _check() -> bool:
            payload = {
                "resource": _ref("cost_management", kessel_type, resource_id),
                "relation": relation,
                "subject": {"subject": _ref("rbac", "principal", subject_id)},
            }
            try:
                resp = requests.post(self._check_url, json=payload, timeout=5)
                if resp.ok:
                    data = resp.json()
                    return data.get("allowed") == "ALLOWED_TRUE" or data.get("allowed", 0) == 1
            except Exception:
                LOG.debug("Resource visibility poll failed", exc_info=True)
            return False

        _poll_until(
            predicate=_check,
            timeout=CONSISTENCY_TIMEOUT,
            label=f"resource visibility {kessel_type}/{resource_id} for {subject_id}",
        )

    def _rbac_to_tuples(self, workspace_id: str, username: str, access: dict) -> list[dict]:
        """Convert an RBAC access dict to a list of Relations API tuples."""
        tuples: list[dict] = []
        principal_id = f"redhat/{username}"

        for koku_type, operations in access.items():
            kessel_type = KOKU_TO_KESSEL_TYPE_MAP.get(koku_type)
            if not kessel_type:
                continue

            if not isinstance(operations, dict):
                continue

            for verb, value in operations.items():
                if not value:
                    continue

                relation_suffix = VERB_TO_RELATION_SUFFIX.get(verb)
                if not relation_suffix:
                    continue

                tag = uuid.uuid4().hex[:8]
                role_id = f"e2e-role-{kessel_type}-{relation_suffix}-{tag}"
                rb_id = f"e2e-rb-{kessel_type}-{relation_suffix}-{tag}"

                relation_name = f"t_cost_management_{kessel_type}_{relation_suffix}"

                tuples.extend([
                    _tuple("rbac", "role", role_id, relation_name, "rbac", "principal", "*"),
                    _tuple("rbac", "role_binding", rb_id, "t_granted", "rbac", "role", role_id),
                    _tuple("rbac", "role_binding", rb_id, "t_subject", "rbac", "principal", principal_id),
                    _tuple("rbac", "workspace", workspace_id, "t_binding", "rbac", "role_binding", rb_id),
                ])

                self._created_items.extend([
                    {"ns": "rbac", "name": "role", "id": role_id, "relation": relation_name},
                    {"ns": "rbac", "name": "role_binding", "id": rb_id, "relation": "t_granted"},
                    {"ns": "rbac", "name": "role_binding", "id": rb_id, "relation": "t_subject"},
                ])

        return tuples

    def _create_tuples(self, tuples: list[dict]) -> None:
        """POST tuples to the Relations API."""
        payload = {"upsert": True, "tuples": tuples}
        resp = requests.post(self._tuples_url, json=payload, timeout=10)
        if not resp.ok:
            LOG.error("Failed to create tuples: %s %s", resp.status_code, resp.text)
        resp.raise_for_status()

    def _delete_tuples(self, namespace: str, name: str, obj_id: str, relation: str) -> None:
        """DELETE tuples matching a filter."""
        params = {
            "filter.resource_namespace": namespace,
            "filter.resource_type": name,
            "filter.resource_id": obj_id,
            "filter.relation": relation,
        }
        try:
            requests.delete(self._tuples_url, params=params, timeout=10)
        except Exception:
            LOG.debug("Cleanup failed for %s/%s:%s#%s", namespace, name, obj_id, relation, exc_info=True)
