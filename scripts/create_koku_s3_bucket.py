#!/usr/bin/env python3
""" Create s3 bucket """
import json
import os

import boto3


def create_s3_bucket():
    bucket_name = os.environ.get("S3_BUCKET_NAME")
    region = os.environ.get("S3_REGION", "us-east-1")

    s3_client = boto3.client("s3")

    # s3 create bucket will fail if LocationConstraint is
    # passed and region is 'us-east-1'
    # https://github.com/boto/boto3/issues/125
    if region == "us-east-1":
        s3_client.create_bucket(Bucket=bucket_name)
    else:
        s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={"LocationConstraint": region})

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Principal": {"AWS": os.environ.get("S3_OWNER_ARN")},
                "Sid": "AllObjectPut",
                "Effect": "Allow",
                "Action": ["s3:PutObject", "s3:GetObject"],
                "Resource": f"arn:aws:s3:::{bucket_name}/*",
            }
        ],
    }

    s3_client.put_bucket_policy(Policy=json.dumps(policy), Bucket=bucket_name)


if "__main__" in __name__:
    create_s3_bucket()
