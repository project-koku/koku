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
        s3_resource = boto3.resource("s3", **credentials)
        s3_bucket = s3_resource.Bucket(bucket_name)
        object_keys = [s3_object.key for s3_object in s3_bucket.objects.filter(Prefix=file_prefix)]
        for key in object_keys:
            s3_resource.Object(bucket_name, key).delete()
        print(f"Removing s3 files for prefix: {file_prefix}")

    client = boto3.client("glue", **credentials)
    try:
        client.delete_database(Name=schema)
        print(f"Deleteing database: {schema}")
    except Exception:
        print(f"Failed to delete db: {schema}, its possible it was already deleted")


if __name__ == "__main__":
    clear_glue_data()
