#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
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
    "local_providers/insights_local",
    "pvc_dir/insights_local",
    "pvc_dir/processing",
    "parquet_data",
    "hadoop",
    "metastore",
    "presto",
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
