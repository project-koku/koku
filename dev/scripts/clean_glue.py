#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Clear out our glue testing data."""
import os

import boto3


def clear_glue_data():
    bucket_name = os.environ.get("S3_BUCKET_NAME")
    schema = f"org{os.environ.get('ORG')}"
    credentials = {
        "aws_access_key_id": os.environ.get("TRINO_AWS_ACCESS_KEY_ID"),
        "aws_secret_access_key": os.environ.get("TRINO_AWS_SECRET_ACCESS_KEY"),
    }
    path_prefixes = {
        "s3_csv_path": f"data/csv/{schema}",
        "s3_parquet_path": f"data/parquet/{schema}",
        "s3_daily_parquet": f"data/parquet/daily/{schema}",
    }

    for _, file_prefix in path_prefixes.items():
        s3_client = boto3.client("s3", **credentials)
        paginator = s3_client.get_paginator("list_objects_v2")
        for obj_list in paginator.paginate(Bucket=bucket_name, Prefix=file_prefix):
            if "Contents" in obj_list:
                keys = [{"Key": x["Key"]} for x in obj_list["Contents"]]
                s3_client.delete_objects(Bucket=bucket_name, Delete={"Objects": keys})
        print(f"Removed s3 files for prefix: {file_prefix}")

    glue_client = boto3.client("glue", **credentials)
    try:
        glue_client.delete_database(Name=schema)
        print(f"Deleting database: {schema}")
    except Exception:
        print(f"Failed to delete db: {schema}, its possible it was already deleted")


if __name__ == "__main__":
    clear_glue_data()
