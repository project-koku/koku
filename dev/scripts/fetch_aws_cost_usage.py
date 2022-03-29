#!/usr/bin/env python3
""" download cost-usage report from s3 """
import json
import logging
import os
import re
import sys

import boto3
import botocore

try:
    S3_BUCKET = sys.argv[1]
except IndexError:
    print(f"usage: {sys.argv[0]} [s3_bucket_name]")
    sys.exit()

CACHE_DIR = "./aws_cost_usage/"
ETAG_FILE = CACHE_DIR + "etags.json"

logging.basicConfig()
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


def load_json(filename):
    """load a json file"""
    json_file = None
    try:
        with open(filename) as json_fh:
            json_file = json.load(json_fh)
    except TypeError:
        json_file = json.load(filename)
    except OSError:
        json_file = json.loads("{}")
    except ValueError:
        LOG.error("Unable to read %s", filename)
    return json_file


def save_json(filename, data):
    """save a json file"""
    try:
        json.dump(data, open(filename, "w+"))
    except TypeError:
        json.dump(data, filename)
    except OSError:
        raise


def retrieve_files():
    """fetch files from s3 bucket"""
    etags = load_json(ETAG_FILE)

    LOG.info("Connecting to S3...")
    s3_resource = boto3.resource("s3")
    bucket = s3_resource.Bucket(S3_BUCKET)

    for objsumm in bucket.objects.all():
        search = re.search(r"(.*)\/(.*)", objsumm.key)
        if search:
            groups = search.groups()
            path = groups[0]
            if not os.path.isdir(CACHE_DIR + path):
                os.makedirs(CACHE_DIR + path)

        # check etags/md5
        if objsumm.key in etags.keys() and objsumm.e_tag == etags.get(objsumm.key, None):
            continue
        else:
            LOG.debug("%s == %s", objsumm.e_tag, etags.get(objsumm.key, None))
            LOG.info("checksums do not match. retrieving %s from s3...", objsumm.key)
            etags[objsumm.key] = objsumm.e_tag

            try:
                bucket.download_file(objsumm.key, CACHE_DIR + objsumm.key)
                save_json(ETAG_FILE, etags)
            except botocore.exceptions.ClientError as exc:
                LOG.error(exc)


def main():
    """main"""
    if not os.path.isdir(CACHE_DIR):
        os.mkdir(CACHE_DIR)
    retrieve_files()


if "__main__" in __name__:
    try:
        main()
    except KeyboardInterrupt:
        print("Ctrl+C detected. Exiting...")
