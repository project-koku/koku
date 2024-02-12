#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Script to render valid SQL from a Jinja template."""
import argparse
import datetime
from uuid import uuid4

from jinjasql import JinjaSql


def valid_date(date_string):
    """Create date from date string."""
    try:
        datetime.datetime.strptime(date_string, "%Y-%m-%d")
    except ValueError:
        msg = f"{date_string} is an unsupported date format."
        raise argparse.ArgumentTypeError(msg)
    return date_string


def id_list(ids):
    return ids.split(",")


def quote_sql_string(value):
    """
    If "value" is a string type, escapes single quotes in the string
    and returns the string enclosed in single quotes.
    Thank you to https://towardsdatascience.com/a-simple-approach-to-templated-sql-queries-in-python-adc4f0dc511
    """
    if isinstance(value, str):
        new_value = str(value)
        new_value = new_value.replace("'", "''")
        return f"'{new_value}'"
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--file", dest="sql_file", required=True, help="path to SQL template file")
    parser.add_argument("-o", "--output-file", dest="output_file", required=False, help="path to output SQL file")
    parser.add_argument(
        "-s",
        "--start-date",
        metavar="YYYY-MM-DD",
        dest="start_date",
        required=False,
        type=valid_date,
        default=datetime.datetime.utcnow().date().replace(day=1).isoformat(),
        help="Date to start generating data (YYYY-MM-DD)",
    )
    parser.add_argument(
        "-e",
        "--end-date",
        metavar="YYYY-MM-DD",
        dest="end_date",
        required=False,
        type=valid_date,
        default=datetime.datetime.utcnow().date().isoformat(),
        help="Date to end generating data (YYYY-MM-DD). Default is today.",
    )
    parser.add_argument("-d", "--schema", dest="schema", required=False, default="org1234567")
    parser.add_argument(
        "-b", "--bill-ids", dest="bill_ids", required=False, type=id_list, help="A comma separated list of bill IDs"
    )
    parser.add_argument("-c", "--cluster-id", dest="cluster_id", required=False, help="An OpenShift cluster ID")
    parser.add_argument(
        "--aws-uuid", dest="aws_provider_uuid", required=False, help="An provider UUID for an AWS provider"
    )
    parser.add_argument(
        "--ocp-uuid", dest="ocp_provider_uuid", required=False, help="An provider UUID for an OpenShift provider"
    )
    parser.add_argument(
        "--azure-uuid", dest="azure_provider_uuid", required=False, help="An provider UUID for an Azure provider"
    )
    parser.add_argument("--markup", dest="markup", required=False, help="A decimal value for markup")
    args = parser.parse_args()

    arg_dict = vars(args)
    arg_dict["uuid"] = str(uuid4()).replace("-", "_")
    sql_file = arg_dict.pop("sql_file")
    output_file = arg_dict.pop("output_file")

    with open(sql_file) as f:
        sql_template = f.read()

    jinja_sql = JinjaSql()
    sql_query, bind_params = jinja_sql.prepare_query(sql_template, arg_dict)

    bind_params = [quote_sql_string(val) for val in bind_params]

    query = sql_query % tuple(bind_params)

    if output_file:
        with open(output_file, "w") as f:
            f.write(query)
    else:
        print(query)
