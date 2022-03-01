#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Script to render valid SQL from a Jinja template."""
import argparse
import datetime

from jinja2 import Template


def valid_date(date_string):
    """Create date from date string."""
    try:
        datetime.datetime.strptime(date_string, "%Y-%m-%d")
    except ValueError:
        msg = f"{date_string} is an unsupported date format."
        raise argparse.ArgumentTypeError(msg)
    return date_string


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-f", "--file", dest="template_file", required=True, help="path to Nise static YAML template file"
    )
    parser.add_argument(
        "-o", "--output-file", dest="output_file", required=False, help="path to output nise static YAML file"
    )
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

    args = parser.parse_args()

    with open(args.template_file, "r") as f:
        nise_template = f.read()

    t = Template(nise_template)
    nise_static = t.render(start_date=args.start_date, end_date=args.end_date)

    if args.output_file:
        with open(args.output_file, "w") as f:
            f.write(nise_static)
    else:
        print(nise_static)
