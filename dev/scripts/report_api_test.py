import datetime
import pprint

import requests


CLOUD_SOURCES = ["aws", "azure", "gcp"]
OPENSHIFT_SOURCE = ["openshift"]
SOURCES = CLOUD_SOURCES + OPENSHIFT_SOURCE

REPORT_ENDPOINTS = {
    "aws": ["costs", "instance-types", "storage"],
    "azure": ["costs", "instance-types", "storage"],
    "gcp": ["costs", "instance-types", "storage"],
    "openshift": ["costs", "compute", "memory", "volumes"],
}

DELTA = {
    "costs": "cost",
    "instance-types": "usage",
    "storage": "usage",
    "compute": "usage",
    "memory": "usage",
    "volumes": "usage",
}

GROUP_BYS = {
    "aws": ["account", "az", "instance_type", "region", "service", "storage_type", "product_family"],
    "azure": ["subscription_guid", "resource_location", "instance_type", "service_name"],
    "gcp": ["account", "region", "service", "gcp_project", "instance_type"],
    "openshift": ["project", "cluster", "node"],
}

TIMES = {
    "",
    "&filter[time_scope_value]=-1&filter[resolution]=monthly",
    "&filter[time_scope_value]=-1&filter[resolution]=daily",
    "&filter[time_scope_value]=-2&filter[resolution]=monthly",
    "&filter[time_scope_value]=-2&filter[resolution]=daily",
    f"&start_date={datetime.datetime.utcnow().date().replace(day=1)}&end_date={datetime.datetime.utcnow().date()}",
}


BASE_URL = "http://127.0.0.1:8000/api/cost-management/v1/reports"
ERRORS = []


def print_response(response):
    """Print status on the API."""
    print(f"Response for {url}")
    if response.status_code == 200:
        # Green text
        print(f"\033[1;32;40m  {response.status_code} {response.reason}\033[1;37;40m")
    else:
        # Red text
        print(f"\033[1;31;40m  {response.status_code} {response.reason}\033[1;37;40m")
        # print(response.json())
    print(f"  {response.elapsed.total_seconds()} seconds elapsed.")


def call_api(url):
    """Call the API."""
    response = requests.get(url)
    print_response(response)
    if response.status_code != 200:
        ERRORS.append(url)


for source in SOURCES:
    for endpoint in REPORT_ENDPOINTS[source]:
        url = f"{BASE_URL}/{source}/{endpoint}/"
        call_api(url)
        for group_by in GROUP_BYS[source]:
            for time in TIMES:
                url = f"{BASE_URL}/{source}/{endpoint}/?group_by[{group_by}]=*{time}"
                call_api(url)

                url = f"{BASE_URL}/{source}/{endpoint}/?group_by[{group_by}]=*&filter[limit]=1{time}"
                call_api(url)

                url = f"{BASE_URL}/{source}/{endpoint}/?group_by[{group_by}]=*&filter[limit]=10&filter[offset]=0{time}"
                call_api(url)

            url = f"{BASE_URL}/{source}/{endpoint}/?group_by[{group_by}]=*&delta={DELTA[endpoint]}"
            call_api(url)


if ERRORS:
    print("The following API calls failed")
    pprint.pprint(ERRORS)
else:
    print("All APIs returned 200s.")
