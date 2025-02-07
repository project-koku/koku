#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Clear out our glue testing data."""
import argparse
import os

import boto3


def delete_glue_data(schema):
    endpoint = os.environ.get("S3_ENDPOINT")
    bucket_name = os.environ.get("S3_BUCKET_NAME")
    credentials = {
        "aws_access_key_id": os.environ.get("S3_ACCESS_KEY"),
        "aws_secret_access_key": os.environ.get("S3_SECRET"),
        "region_name": os.environ.get("S3_REGION") or "us-east-1",
    }
    path_prefixes = {
        "s3_csv_path": f"data/csv/{schema}",
        "s3_parquet_path": f"data/parquet/{schema}",
        "s3_daily_parquet": f"data/parquet/daily/{schema}",
        "s3_schema_db_path": f"data/{schema}",
    }

    s3_client = boto3.client("s3", endpoint_url=endpoint, **credentials)
    for _, file_prefix in path_prefixes.items():
        paginator = s3_client.get_paginator("list_objects_v2")
        for obj_list in paginator.paginate(Bucket=bucket_name, Prefix=file_prefix):
            if "Contents" in obj_list:
                s3_client.delete_objects(
                    Bucket=bucket_name, Delete={"Objects": [{"Key": x["Key"]} for x in obj_list["Contents"]]}
                )
        print(f"Removed s3 files for prefix: {file_prefix}")

    # this client requires AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY set in env
    glue_client = boto3.client("glue", region_name="us-east-1")
    try:
        glue_client.delete_database(Name=schema)
        print(f"Deleting database: {schema}")
    except Exception as e:
        print(f"Failed to delete db: {schema}, its possible it was already deleted: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("schema")
    args = parser.parse_args()

    delete_glue_data(args.schema)


if __name__ == "__main__":
    main()
