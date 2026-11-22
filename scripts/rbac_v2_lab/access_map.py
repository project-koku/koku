#!/usr/bin/env python3
"""Simulate koku's RBAC v2 backend against the lab and print the access map.

Mirrors `koku.koku.rbac.RbacV2Service`: read effective bindings for a principal,
expand role permissions, and fold them into the v1 `user.access` shape.
"""
import base64
import json
import os
import urllib.parse
import urllib.request

BASE = os.environ.get("BASE", "http://localhost:9080/api/rbac/v2")
IDENTITY = os.environ.get(
    "IDENTITY",
    base64.b64encode(
        json.dumps(
            {
                "identity": {
                    "account_number": "1234567",
                    "org_id": "1234567",
                    "type": "User",
                    "user": {
                        "username": "admin",
                        "user_id": "u-admin",
                        "is_org_admin": True,
                        "email": "a@b.c",
                    },
                }
            }
        ).encode()
    ).decode(),
)

RESOURCE_TYPES = {
    "aws.account": ["read"],
    "aws.organizational_unit": ["read"],
    "azure.subscription_guid": ["read"],
    "gcp.account": ["read"],
    "gcp.project": ["read"],
    "openshift.cluster": ["read"],
    "openshift.node": ["read"],
    "openshift.project": ["read"],
    "cost_model": ["read", "write"],
    "settings": ["read", "write"],
}
WRITE_VERBS = {"write", "edit", "create", "delete", "move"}


def get(url):
    req = urllib.request.Request(url, headers={"x-rh-identity": IDENTITY})
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def role_permissions(role_id, cache):
    if role_id in cache:
        return cache[role_id]
    role = get(f"{BASE}/roles/{role_id}/")
    perms = []
    for p in role.get("permissions") or []:
        if isinstance(p, str):
            perms.append(p)
        else:
            perms.append(f"{p['application']}:{p['resource_type']}:{p['operation']}")
    cache[role_id] = perms
    return perms


def target_ops(verb, operations):
    """Return the koku operations a v1-style verb grants for a resource type."""
    if verb == "*":
        return list(operations)
    if verb in WRITE_VERBS:
        return [op for op in ("write", "read") if op in operations]
    if verb == "read":
        return ["read"] if "read" in operations else []
    return []


def apply_permission(access, permission, workspace):
    """Fold one `app:resource:verb` permission into the access map."""
    try:
        application, resource_type, verb = permission.split(":")
    except ValueError:
        return
    if application != "cost-management":
        return

    resource_types = list(RESOURCE_TYPES) if resource_type == "*" else [resource_type]
    for res_type in resource_types:
        operations = RESOURCE_TYPES.get(res_type)
        if not operations:
            continue
        for operation in target_ops(verb, operations):
            access[res_type][operation].append(workspace)


def access_for(user_id):
    params = {
        "limit": 100,
        "granted_subject_type": "principal",
        "granted_subject.principal.user_id": user_id,
        "exclude_sources": "none",
        "fields": "role(id,name),resource(id,name)",
    }
    bindings = get(f"{BASE}/role-bindings/?{urllib.parse.urlencode(params)}")["data"]

    access = {rt: {op: [] for op in ops} for rt, ops in RESOURCE_TYPES.items()}
    cache = {}
    for binding in bindings:
        workspace = (binding.get("resource") or {}).get("name")
        if not workspace:
            continue
        for permission in role_permissions(binding["role"]["id"], cache):
            apply_permission(access, permission, workspace)

    for ops in access.values():
        for operation, ids in ops.items():
            ops[operation] = ["*"] if "*" in ids else list(dict.fromkeys(ids))
    return access


if __name__ == "__main__":
    for user_id in ("user1", "user2"):
        print(f"-- {user_id}")
        print(json.dumps(access_for(user_id), indent=2, sort_keys=True))
