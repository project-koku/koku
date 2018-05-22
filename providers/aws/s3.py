"""Helper utility module to wrap up common AWS S3 operations."""
import logging
import os

import boto3

from masu.providers import DATA_DIR

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def get_file_from_s3(customer_schema, region, bucket, key):
    """
    Download an S3 object to file.

    Args:
        customer_schema (str): The customer database schema name.
        region (str): The AWS region the bucket resides in.
        bucket (str): The S3 bucket the object is stored in.
        key (str): The S3 object key identified.

    Returns:
        str: The path and file name of the saved file

    """
    s3_file = key.split('/')[-1]
    file_path = f'{DATA_DIR}/{customer_schema}/aws'
    file_name = f'{file_path}/{s3_file}'
    # Make sure the data directory exists
    os.makedirs(file_path, exist_ok=True)

    s3_bucket = boto3.resource('s3', region_name=region).Bucket(bucket)

    logger.info('Downloading %s to %s', s3_file, file_name)
    s3_bucket.download_file(key, file_name)

    return file_name
