#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import json
import os
import shutil
import sys
import tarfile
import tempfile
import uuid
from datetime import datetime


def generate_package(csv_files, cluster_id):
    """
    Generate tarball package for OpenShift usage report files.
    The tarball will contain the following:
    1. .csv report file re-named to be prepended with a uuid.
    1. manifest.json file:
        Keys: file       - name of the file .csv report file
                date       - datetime for when the package was created
                uuid       - identifier unique to this report package
                cluster_id - unique identifier for OCP cluster
    Args:
        csv_files  - list of full path to the report files to be bundled
        cluster_id - unique identifier for OCP cluster
    Returns:
        (None) : payload.tar.gz file is created in the directory
                    that the script is executed from.
    """
    # Generate a temporary directory to stage the package contents.
    temp_dir = tempfile.mkdtemp()

    # Generate UUID and capture timestamp.
    file_uuid = uuid.uuid4()
    today = datetime.today()

    # Copy the .csv report file to the staging directory with uuid prepended.
    dst_file_list = []
    for csv_file in csv_files:
        src_file_name = os.path.basename(csv_file)
        dst_file_name = f"{file_uuid}_{src_file_name}"
        dst_file = f"{temp_dir}/{dst_file_name}"
        shutil.copy(csv_file, dst_file)
        dst_file_list.append(dst_file_name)

    # Populate package dictionary
    package_dict = {}
    package_dict["files"] = dst_file_list
    package_dict["date"] = str(today)
    package_dict["uuid"] = str(file_uuid)
    package_dict["cluster_id"] = cluster_id

    # Write dictionary to manifest.json file in staging directory
    manifest_file = "{}/{}".format(temp_dir, "manifest.json")
    with open(manifest_file, "w") as file:
        file.write(json.dumps(package_dict))

    # Create .tar.gz of the temporary directory contents.
    tarball_file = "{}/{}".format(os.getcwd(), "payload.tar.gz")
    with tarfile.open(tarball_file, "w:gz") as tar:
        tar.add(temp_dir, arcname=os.path.sep)

    # Cleanup staging area
    shutil.rmtree(temp_dir)


def main(args):
    """
    Packages OpenShift usage reports into payload for upload.
    The upload payload is intended for the Insights Upload service
    the format of the package contents must be consistent with what
    Masu is expected to ensure proper ingestion of OCP report data.
    Args:
        args   - Script arguments.
            Positions:  0 - .csv report file to be packaged.
                        1 - OpenShift cluster ID
    Returns:
        (None) : payload.tar.gz file is created in the directory
                    that the script is executed from.
    """
    if len(args) != 2:
        print("python ocp_csv_package.py <.csv file> <cluster_id>")
        exit(2)

    csv_files = args[0]
    parsed_file_list = csv_files.split(",")

    csv_files = []
    for csv_file in parsed_file_list:
        full_csv_path = os.path.abspath(csv_file)
        if not os.path.isfile(full_csv_path):
            print("Unable to locate file:", full_csv_path)
            exit(2)
        csv_files.append(full_csv_path)

    cluster_id = args[1]
    if cluster_id is None:
        print("Cluster ID not specified")
        exit(2)
    generate_package(csv_files, cluster_id)


if "__main__" in __name__:
    main(sys.argv[1:])
