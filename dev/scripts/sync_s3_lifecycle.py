#!/usr/bin/env python3
# noqa
""" sync s3 lifecycle policy """
import os
from distutils.util import strtobool  # noreorder

import boto3


def sync_s3_lifecycle():
    s3 = boto3.resource("s3")
    bucket_lifecycle_configuration = s3.BucketLifecycleConfiguration(os.environ.get("S3_BUCKET_NAME"))
    bucket_lifecycle_configuration.put(
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID": "s3_lifecycle_policy",
                    "Status": "Enabled",
                    "Filter": {"Prefix": os.environ.get("S3_BUCKET_PATH")},
                    "Transitions": [
                        {"Days": int(os.environ.get("S3_IA_TRANSITION")), "StorageClass": "STANDARD_IA"},
                        {"Days": int(os.environ.get("S3_GLACIER_TRANSITION")), "StorageClass": "GLACIER"},
                    ],
                }
            ]
        }
    )


if "__main__" in __name__:
    if strtobool(os.environ.get("ENABLE_S3_ARCHIVING") or "False"):
        sync_s3_lifecycle()
