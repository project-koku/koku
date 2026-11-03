#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""RTU test setup against an ephemeral namespace, run inside the toolbox pod (see testdata.sh).

Talks to the in-cluster services with an x-rh-identity header for one test org, the way
the platform does: no gateway, no credentials. Only needs python3 + requests, which the
nise-populator image has.

Commands:
    sources        register the two OCP clusters in sources-api (koku creates the providers)
    wait-sources   wait until koku has a provider for both clusters
    cost-models    create one price list (rates from the koku dev on-prem cost model) and one
                   cost model per cluster, both attached to that price list
    remove-rate    PUT the price list without the rate --custom-name (default: the first rate)
    show           print sources, price list rates and cost models as koku sees them
"""
import argparse
import base64
import json
import os
import sys
import time
from datetime import date
from datetime import timedelta

import requests

ORG_ID = os.environ.get("RTU_ORG_ID", "7654321")
ACCOUNT = os.environ.get("RTU_ACCOUNT", ORG_ID)
USERNAME = os.environ.get("RTU_USER", "rtu-tester")
SOURCES_API = os.environ.get("SOURCES_API", "http://sources-api-svc:8000/api/sources/v3.1")
KOKU_API = os.environ.get("KOKU_API", "http://koku-clowder-api:8000/api/cost-management/v1")
COST_MODEL_JSON = os.environ.get("COST_MODEL_JSON", "/tmp/rtu/openshift_on_prem_cost_model.json")
CLUSTERS = {"rtu-cluster-a": "RTU cluster A", "rtu-cluster-b": "RTU cluster B"}
PRICE_LIST_NAME = "RTU shared price list"


def headers():
    identity = {
        "identity": {
            "account_number": ACCOUNT,
            "org_id": ORG_ID,
            "type": "User",
            "user": {"username": USERNAME, "email": f"{USERNAME}@example.com", "is_org_admin": True},
            "internal": {"org_id": ORG_ID},
        },
        "entitlements": {"cost_management": {"is_entitled": True}},
    }
    return {
        "x-rh-identity": base64.b64encode(json.dumps(identity).encode()).decode(),
        "Content-Type": "application/json",
    }


def call(method, url, **kwargs):
    response = requests.request(method, url, headers=headers(), timeout=120, **kwargs)
    if response.status_code >= 400:
        sys.exit(f"{method} {url} -> {response.status_code}: {response.text[:800]}")
    return response.json() if response.text else {}


def koku_sources():
    return {s["name"]: s for s in call("GET", f"{KOKU_API}/sources/", params={"limit": 100})["data"]}


def price_list():
    for pl in call("GET", f"{KOKU_API}/price-lists/", params={"limit": 100})["data"]:
        if pl["name"] == PRICE_LIST_NAME:
            return call("GET", f"{KOKU_API}/price-lists/{pl['uuid']}/")
    return None


def cmd_sources(_):
    ocp_type_id = call("GET", f"{SOURCES_API}/source_types", params={"filter[name]": "openshift"})["data"][0]["id"]
    app_type_id = next(
        a["id"]
        for a in call("GET", f"{SOURCES_API}/application_types")["data"]
        if "Cost Management" in (a.get("display_name") or "")
    )
    existing = {s["name"] for s in call("GET", f"{SOURCES_API}/sources", params={"limit": 1000})["data"]}
    for cluster_id, name in CLUSTERS.items():
        if name in existing:
            print(f"source {name} already registered")
            continue
        payload = {
            "sources": [
                {
                    "name": name,
                    "source_type_id": ocp_type_id,
                    "source_type_name": "openshift",
                    "source_ref": cluster_id,
                }
            ],
            "applications": [{"application_type_id": app_type_id, "source_name": name}],
            "authentications": [
                {
                    "authtype": "token",
                    "resource_name": "/insights/platform/cost-management",
                    "resource_type": "Application",
                }
            ],
            "endpoints": [],
        }
        call("POST", f"{SOURCES_API}/bulk_create", json=payload)
        print(f"registered source {name} (cluster {cluster_id})")


def cmd_wait_sources(args):
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        sources = koku_sources()
        ready = {name: sources[name]["uuid"] for name in CLUSTERS.values() if sources.get(name, {}).get("uuid")}
        if len(ready) == len(CLUSTERS):
            for name, provider_uuid in ready.items():
                print(f"{name}: provider {provider_uuid}")
            return
        time.sleep(15)
    sys.exit(f"koku did not create providers for {list(CLUSTERS.values())} within {args.timeout}s")


def cmd_cost_models(_):
    template = json.load(open(COST_MODEL_JSON))
    sources = koku_sources()
    pl = price_list()
    if not pl:
        first_of_previous_month = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
        pl = call(
            "POST",
            f"{KOKU_API}/price-lists/",
            json={
                "name": PRICE_LIST_NAME,
                "description": "RTU hardening test price list, shared by both RTU cost models",
                "currency": "USD",
                "effective_start_date": str(first_of_previous_month),
                "effective_end_date": "2099-12-31",
                "rates": template["rates"],
            },
        )
        print(f"created price list {pl['uuid']} with {len(pl['rates'])} rates")
    existing = {cm["name"] for cm in call("GET", f"{KOKU_API}/cost-models/", params={"limit": 100})["data"]}
    for cluster_id, source_name in CLUSTERS.items():
        name = f"RTU cost model {cluster_id}"
        if name in existing:
            print(f"cost model {name} already exists")
            continue
        cost_model = call(
            "POST",
            f"{KOKU_API}/cost-models/",
            json={
                "name": name,
                "description": "RTU hardening test cost model",
                "source_type": "OCP",
                "source_uuids": [sources[source_name]["uuid"]],
                "price_list_uuids": [pl["uuid"]],
                "distribution_info": template.get("distribution_info"),
                "currency": "USD",
            },
        )
        print(f"created cost model {cost_model['uuid']} ({name})")


def cmd_remove_rate(args):
    pl = price_list() or sys.exit("no RTU price list; run cost-models first")
    rates = pl["rates"]
    target = args.custom_name or rates[0]["custom_name"]
    kept = [r for r in rates if r.get("custom_name") != target]
    if len(kept) == len(rates):
        sys.exit(f"rate {target!r} not in the price list")
    removed = next(r for r in rates if r.get("custom_name") == target)
    body = {k: pl[k] for k in ("name", "description", "currency", "effective_start_date", "effective_end_date")}
    body["rates"] = kept
    call("PUT", f"{KOKU_API}/price-lists/{pl['uuid']}/", json=body)
    print(json.dumps({"removed_custom_name": target, "removed_rate_id": removed.get("rate_id")}))


def cmd_rbac_check(_):
    """sources-api asks RBAC for the caller's access; RBAC must know the org (404 otherwise)."""
    response = requests.get(
        "http://rbac-service:8000/api/rbac/v1/access/",
        params={"application": "sources"},
        headers=headers(),
        timeout=60,
    )
    print(f"org {ORG_ID}: RBAC access -> {response.status_code} {response.text[:200]}")


def cmd_show(_):
    print("sources:", {name: s.get("uuid") for name, s in koku_sources().items()})
    pl = price_list()
    if pl:
        print("price list:", pl["uuid"], [(r.get("custom_name"), r.get("rate_id")) for r in pl["rates"]])
    for cm in call("GET", f"{KOKU_API}/cost-models/", params={"limit": 100})["data"]:
        print("cost model:", cm["uuid"], cm["name"], [s["uuid"] for s in cm.get("sources", [])])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sources").set_defaults(func=cmd_sources)
    wait = sub.add_parser("wait-sources")
    wait.add_argument("--timeout", type=int, default=900)
    wait.set_defaults(func=cmd_wait_sources)
    sub.add_parser("cost-models").set_defaults(func=cmd_cost_models)
    remove = sub.add_parser("remove-rate")
    remove.add_argument("--custom-name")
    remove.set_defaults(func=cmd_remove_rate)
    sub.add_parser("show").set_defaults(func=cmd_show)
    sub.add_parser("rbac-check").set_defaults(func=cmd_rbac_check)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
