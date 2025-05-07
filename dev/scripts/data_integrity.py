#!/usr/bin/env python
#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import argparse
import datetime
import logging
import os
from datetime import timedelta

import ciso8601
import requests
from dateutil import parser
from dateutil.rrule import DAILY
from dateutil.rrule import rrule
from django.conf import settings

LOG = logging.getLogger(__name__)

# All tables
ALL_TABLES = {
    "AWS": "reporting_awscostentrylineitem_daily_summary",
    "OCPAWS": "reporting_ocpawscostlineitem_project_daily_summary_p",
    "AZURE": "reporting_azurecostentrylineitem_daily_summary",
    "OCPAZURE": "reporting_ocpazurecostlineitem_project_daily_summary_p",
    "GCP": "reporting_gcpcostentrylineitem_daily_summary",
    "OCPGCP": "reporting_ocpgcpcostlineitem_project_daily_summary_p",
    "OCPALL": "reporting_ocpallcostlineitem_project_daily_summary_p",
    "OCP": "reporting_ocpusagelineitem_daily_summary",
}

ALL_TRINO_TABLES = {
    "AWS": "aws_line_items",
    "AWSDAILY": "aws_line_items_daily",
    "AZURE": "azure_line_items",
    "AZUREDAILY": "azure_openshift_daily",
    "GCP": "gcp_line_items",
    "GCPDAILY": "gcp_line_items_daily",
    "OCPAWS": "reporting_ocpawscostlineitem_project_daily_summary",
    "OCPAZURE": "reporting_ocpazurecostlineitem_project_daily_summary",
    "OCPGCP": "reporting_ocpgcpcostlineitem_project_daily_summary",
    "OCP": "reporting_ocpusagelineitem_daily_summary",
}


class ArgError(Exception):
    """Errors specific to missing args"""

    pass


class QueryError(Exception):
    """Errors specific to given query"""


def get_list_of_dates(start_date, end_date):
    """Return a list of days from the start date till the end date."""
    end_midnight = end_date
    start_midnight = start_date
    try:
        start_midnight = ciso8601.parse_datetime(start_date).replace(hour=0, minute=0, second=0, microsecond=0)
    except TypeError:
        start_midnight = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

    try:
        end_midnight = ciso8601.parse_datetime(end_date).replace(hour=0, minute=0, second=0, microsecond=0)
    except TypeError:
        end_midnight = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

    days = (end_midnight - start_midnight + datetime.timedelta(days=1)).days

    # built-in range(start, end, step) requires (start < end) == True
    day_range = range(days, 0) if days < 0 else range(0, days)
    output = [(start_midnight + datetime.timedelta(i)).strftime("%Y-%m-%d") for i in day_range]
    return output


def date_range_pair(start_date, end_date, step):
    """Create a range generator for dates.

    Given a start date and end date make a generator that returns a start
    and end date over the interval.

    """
    try:
        start_date = parser.parse(start_date)
    except TypeError:
        start_date = datetime.datetime(start_date.year, start_date.month, start_date.day, tzinfo=settings.UTC)

    try:
        end_date = parser.parse(end_date)
    except TypeError:
        end_date = datetime.datetime(end_date.year, end_date.month, end_date.day, tzinfo=settings.UTC)

    dates = list(rrule(freq=DAILY, dtstart=start_date, until=end_date, interval=step))
    # Special case with only 1 period
    if len(dates) == 1:
        yield start_date.date(), end_date.date()
    else:
        for date in dates:
            if date == start_date and date != end_date:
                continue
            yield start_date.date(), date.date()
            start_date = date + timedelta(days=1)
        if len(dates) != 1 and end_date not in dates:
            yield start_date.date(), end_date.date()


def get_providers_and_tables_for_schema(gabi_url, token, schema):
    # Get relevant tables for providers
    pg_tables = set()
    provider_count = {"AWS": 0, "AZURE": 0, "GCP": 0, "OCP": 0}
    trino_tables = set()

    query = f"select p.type, i.infrastructure_type from api_provider as p left join api_customer as c on p.customer_id = c.id left join api_providerinfrastructuremap as i on p.infrastructure_id = i.id where p.paused = 'false' and p.active = 'true' and p.setup_complete = 'true' and c.schema_name = '{schema}';"  # noqa E501
    data = submit_query_request(gabi_url, token, query)
    query_types = sorted(data["result"][1:])

    # Add relevant tables to list for schema
    for t in query_types:
        if "AWS" == t[0]:
            provider_count["AWS"] += 1
            pg_tables.add(ALL_TABLES["AWS"])
            trino_tables.add(ALL_TRINO_TABLES["AWS"])
            trino_tables.add(ALL_TRINO_TABLES["AWSDAILY"])
        elif "AZURE" == t[0]:
            provider_count["AZURE"] += 1
            pg_tables.add(ALL_TABLES["AZURE"])
            trino_tables.add(ALL_TRINO_TABLES["AZURE"])
            trino_tables.add(ALL_TRINO_TABLES["AZUREDAILY"])
        elif "GCP" == t[0]:
            provider_count["GCP"] += 1
            pg_tables.add(ALL_TABLES["GCP"])
            trino_tables.add(ALL_TRINO_TABLES["GCP"])
            trino_tables.add(ALL_TRINO_TABLES["GCPDAILY"])
        elif "OCP" == t[0]:
            provider_count["OCP"] += 1
            pg_tables.add(ALL_TABLES["OCP"])
            trino_tables.add(ALL_TRINO_TABLES["OCP"])
            if ["AWS", "OCP"] == sorted(t):
                pg_tables.add(ALL_TABLES["OCPAWS"])
                pg_tables.add(ALL_TABLES["OCPALL"])
                trino_tables.add(ALL_TRINO_TABLES["OCPAWS"])
            elif ["AZURE", "OCP"] == sorted(t):
                pg_tables.add(ALL_TABLES["OCPAZURE"])
                pg_tables.add(ALL_TABLES["OCPALL"])
                trino_tables.add(ALL_TRINO_TABLES["OCPAZURE"])
            elif ["GCP", "OCP"] == sorted(t):
                pg_tables.add(ALL_TABLES["OCPGCP"])
                pg_tables.add(ALL_TABLES["OCPALL"])
                trino_tables.add(ALL_TRINO_TABLES["OCPGCP"])

    return pg_tables, trino_tables, provider_count


def get_list_of_active_schema(gabi_url, token, cloud_only=False):
    # Fetch list of active schemas
    schemas = set()
    prov_types = ("AWS", "AZURE", "GCP") if cloud_only else ("AWS", "AZURE", "GCP", "OCP")
    query = f"select distinct(c.schema_name) from api_provider as p left join api_customer as c on p.customer_id = c.id where p.type in {prov_types} and p.paused = 'false' and p.active = 'true' and p.setup_complete = 'true';"  # noqa E501
    query_result = submit_query_request(gabi_url, token, query)
    for i in query_result["result"][1:]:
        schemas.add(i[0])
    return schemas


# GABI #
def submit_query_request(gabi_url, token, query):
    """Submit the query to gabi in the expected shape"""
    query_data = {"query": query}
    headers = {"Authorization": f"Bearer {token}"}
    q_url = f"{gabi_url}/query"

    resp = requests.post(q_url, headers=headers, json=query_data)
    if not resp.ok:
        raise QueryError(f"HTTP {resp.status_code} {resp.reason} : {resp.text}")

    data = resp.json()
    if data["error"]:
        raise QueryError(data["error"])

    return data


def query_table_data(gabi_url, token, schema, table, start_date, end_date, step):
    result_list = None
    for start, end in date_range_pair(start_date, end_date, step):
        query = f"SELECT usage_start, count(*) FROM {schema}.{table} WHERE usage_start between '{start}' and '{end}' group by usage_start order by usage_start;"  # noqa E501
        query_result = submit_query_request(gabi_url, token, query)
        if not result_list:
            result_list = query_result["result"]
        else:
            result_list.extend(x for x in query_result["result"] if x not in result_list)
    return result_list


def check_for_daily_data(table, data, dates):
    daily_data = {}
    missing_daily_data = set()
    for i in data:
        for date in dates:
            if date in i[0]:
                daily_data[date] = True
    for date in dates:
        if not daily_data.get(date):
            missing_daily_data.add(date)
    if missing_daily_data == set():
        return f"All data complete for table: {table}"
    else:
        return f"Missing data for days: {sorted(missing_daily_data)}"


# TRINO #
def query_trino(url, cert, key, query, schema, headers=None, proxies=None):
    # Query trino tables
    auth = (cert, key)
    if not headers:
        headers = {"Accept": "application/json"}
    query_dict = {"query": query, "schema": schema}
    r = requests.post(url, data=query_dict, cert=auth, headers=headers, proxies=proxies)

    return r


def trino_data_validation(trino_url, cert, key, table, schema, start_date, end_date, step):
    provider = "AWS"
    if "azure" in table:
        provider = "AZURE"
    elif "gcp" in table:
        provider = "GCP"
    elif "ocp" in table:
        provider = "OCP"

    date_fields = {
        "AWS": "lineitem_usagestartdate",
        "AZURE": "date",
        "GCP": "usage_start_time",
        "OCP": "usage_start",
    }
    date_field = date_fields[provider]
    query_results = {}
    for start, end in date_range_pair(start_date, end_date, step):
        query = f"select date({date_field}), count(*) from {table} where date({date_field}) between date('{start}') and date('{end}') group by date({date_field}) order by date({date_field})"  # noqa E501
        resp = query_trino(trino_url, cert, key, query, schema)
        if not resp.ok:
            raise QueryError(f"HTTP {resp.status_code} {resp.reason} : {resp.text}")
        data = resp.json()
        for i in data:
            query_results[i.get("_col0")] = i.get("_col1")
    return query_results


def check_for_daily_trino_data(table, data, dates):
    daily_data = {}
    missing_daily_data = set()
    for date in dates:
        if data.get(date):
            daily_data[date] = True
    for date in dates:
        if not daily_data.get(date):
            missing_daily_data.add(date)
    if missing_daily_data == set():
        return f"All data complete for table: {table}"
    else:
        return f"Missing data for days: {sorted(missing_daily_data)}"


def check_data_integrity(  # noqa C901
    gabi_url,
    trino_url,
    token,
    cert,
    key,
    start_date,
    end_date,
    date_step,
    schemas=None,
    collect_schema=False,
    cloud_only=False,
):
    # Query the relating PG tables for a list of schema
    if validate_args(gabi_url, trino_url, token, cert, key, start_date, end_date):
        if not schemas:
            schemas = get_list_of_active_schema(gabi_url, token, cloud_only)
        if collect_schema:
            print(schemas)
            return
        debrief_result = {}
        print(f"Query dates, Start: {start_date}, End: {end_date}, Query date step: {date_step}\n")
        for schema in schemas:
            dates = get_list_of_dates(start_date, end_date)
            pg_tables, trino_tables, provider_counts = get_providers_and_tables_for_schema(gabi_url, token, schema)

            print(
                f"Context for {schema}.\nProviders: {provider_counts}\nPG Tables to query: {pg_tables}\nTrino Tables to query: {trino_tables}\n"  # noqa E501
            )
            trino_query = False
            for pg_table in pg_tables:
                data = query_table_data(gabi_url, token, schema, pg_table, start_date, end_date, date_step)
                daily_result = check_for_daily_data(pg_table, data, dates)
                if "Missing" in daily_result:
                    trino_query = True
                if not debrief_result.get(schema):
                    debrief_result[schema] = {"PG": {}, "TRINO": {}}
                debrief_result[schema]["PG"][pg_table] = daily_result
            if trino_query:
                for t_table in trino_tables:
                    try:
                        data = trino_data_validation(
                            trino_url, cert, key, t_table, schema, start_date, end_date, date_step
                        )
                        daily_result = check_for_daily_trino_data(t_table, data, dates)
                    except Exception:
                        debrief_result[schema]["TRINO"][t_table] = "Error querying data"
                    debrief_result[schema]["TRINO"][t_table] = daily_result
            else:
                debrief_result[schema]["TRINO"] = "PG data complete so skipping trino query"
        print(f"{debrief_result}")


def validate_args(trino_url, gabi_url, token, cert, key, start_date, end_date):
    """Validate that url, token, and query are not empty."""
    LOG.info("Validating arguments")
    if not gabi_url:
        raise ArgError("The gabi instance URL is required")
    if not trino_url:
        raise ArgError("The trino instance URL is required")
    if not token:
        raise ArgError("Your OCP console token is required")
    if not cert:
        raise ArgError("Your turnpike cert is required to interact with trino")
    if not key:
        raise ArgError("Your turnpike key is required to interact with trino")
    if not start_date:
        raise ArgError("Start date required for query")
    if not end_date:
        raise ArgError("End date required for query")

    return True


if __name__ == "__main__":

    def data_integrity_argparser():
        """Initialize parser and set arguments"""
        arg_parser = argparse.ArgumentParser(
            description="data_integrity: Crawl postgres and trino for missing customer data, format the response as json."  # noqa E501
        )
        arg_parser.add_argument(
            "-g",
            "--gabi-url",
            metavar="GABIURL",
            dest="gabi_url",
            required=False,
            help="Gabi instance URL. Can also use env GABI_URL",
        )
        arg_parser.add_argument(
            "-u",
            "--trino-url",
            metavar="TRINOURL",
            dest="trino_url",
            required=False,
            help="Trino instance URL. Can also use env TRINO_URL",
        )
        arg_parser.add_argument(
            "-t",
            "--token",
            metavar="TOKEN",
            dest="token",
            required=False,
            help="Openshift console token. Can also use env OCP_CONSOLE_TOKEN",
        )
        arg_parser.add_argument(
            "-c",
            "--cert",
            metavar="CERT",
            dest="cert",
            required=False,
            help="Trino turnpike cert. Can also use env TRINO_CERT",
        )
        arg_parser.add_argument(
            "-k",
            "--key",
            metavar="KEY",
            dest="key",
            required=False,
            help="Trino turnpike key. Can also use env TRINO_KEY",
        )
        arg_parser.add_argument(
            "-s",
            "--start-date",
            metavar="STARTDATE",
            dest="start_date",
            required=False,
            help="Start date for query",
        )
        arg_parser.add_argument(
            "-e",
            "--end-date",
            metavar="ENDDATE",
            dest="end_date",
            required=False,
            help="End date for query",
        )
        arg_parser.add_argument(
            "-x",
            "--schema",
            nargs="+",
            metavar="SCHEMA",
            dest="schema",
            required=False,
            help="Schema to target",
        )
        arg_parser.add_argument(
            "-j",
            "--date-step",
            metavar="DATESTEP",
            dest="date_step",
            required=False,
            default=5,
            help="Used to break up your queries if they timeout, default is 5",
        )
        arg_parser.add_argument(
            "-l",
            "--collect_schema",
            metavar="COLLECTSCHEMA",
            dest="collect_schema",
            action=argparse.BooleanOptionalAction,
            default=False,
            help="Return the list of schema attempting to query",
        )

        return arg_parser.parse_args()

    def process_args(args):
        """Procerss the parsed arguments to the program"""
        if not args.gabi_url:
            args.gabi_url = os.environ.get("GABI_URL")
        if not args.trino_url:
            args.trino_url = os.environ.get("TRINO_URL")
        if not args.token:
            args.token = os.environ.get("OCP_CONSOLE_TOKEN")
        if not args.cert:
            args.cert = os.environ.get("TRINO_CERT")
        if not args.key:
            args.key = os.environ.get("TRINO_KEY")

        return args

    # Init, get, and process the arguments
    args = data_integrity_argparser()

    # Call the main processing entrypoint
    check_data_integrity(
        args.gabi_url,
        args.trino_url,
        args.token,
        args.cert,
        args.key,
        args.start_date,
        args.end_date,
        args.date_step,
        args.schema,
        args.collect_schema,
    )
