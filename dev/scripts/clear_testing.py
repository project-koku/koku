#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Clear out our local testing directories."""
import argparse
import os
import shutil

TESTING_DIRS = [
    "local_providers/aws_local",
    "local_providers/aws_local_0",
    "local_providers/aws_local_1",
    "local_providers/aws_local_2",
    "local_providers/aws_local_3",
    "local_providers/aws_local_4",
    "local_providers/aws_local_5",
    "local_providers/azure_local",
    "local_providers/azure_local_0",
    "local_providers/azure_local_1",
    "local_providers/gcp_local",
    "local_providers/gcp_local_0",
    "local_providers/gcp_local_1",
    "local_providers/gcp_local_2",
    "local_providers/gcp_local_3",
    "local_providers/insights_local",
    "data/insights_local",
    "data/processing",
    "parquet_data",
]


def main(*args, **kwargs):
    testing_path = kwargs["testing_path"]

    paths_to_clear = [f"{testing_path}/{directory}" for directory in TESTING_DIRS]

    for path in paths_to_clear:
        try:
            print(f"Checking {path}")
            dirs_to_remove = [f.path for f in os.scandir(path) if f.is_dir()]
            for directory in dirs_to_remove:
                print(f"Removing {directory}")
                shutil.rmtree(directory)
        except FileNotFoundError as err:
            print(err)


if __name__ == "__main__":
    PARSER = argparse.ArgumentParser()
    PARSER.add_argument("-p", "--path", dest="testing_path", help="The path to the testing directory", required=True)

    ARGS = vars(PARSER.parse_args())
    main(**ARGS)
