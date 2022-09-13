#!/usr/bin/env python3
from os import environ

import requests

if __name__ == "__main__":
    token = environ.get("GH_TOKEN")
    if not token:
        print("must set GH_TOKEN environment variable")
        print("docs: https://docs.github.com/en/rest/actions/cache")
        exit(1)

    headers = {"Authorization": f"Bearer {token}"}

    owner = environ.get("GH_OWNER") or "project-koku"
    repo = environ.get("GH_REPO") or "koku"
    url = f"http://api.github.com/repos/{owner}/{repo}/actions/caches"

    r = requests.get(url, params={"limit": 1000}, headers=headers).json()
    cache_ids = []
    for resp in r.get("actions_caches", []):
        if cache_id := resp.get("id"):
            cache_ids.append(cache_id)

    for cache_id in cache_ids:
        delete_url = f"{url}/{cache_id}"
        print(f"Calling DELETE {delete_url}")
        r = requests.delete(delete_url, headers=headers)
        print(r)
