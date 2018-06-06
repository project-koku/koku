#
# Copyright 2018 Red Hat, Inc.
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
