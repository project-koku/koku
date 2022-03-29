#!/usr/bin/env python3
""" script to download aws pricing lists """
import json
import logging
import os
from datetime import datetime
from urllib.request import urlopen
from urllib.request import urlretrieve

AWS_API_ENDPOINT = "https://pricing.us-east-1.amazonaws.com"
AWS_PRICING_INDEX = AWS_API_ENDPOINT + "/offers/v1.0/aws/index.json"
PRICE_INDEX = "index.json"
CACHE_DIR = "./aws_pricing/"

logging.basicConfig(level=logging.DEBUG)
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


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


def collect_data():
    """fetch pricing data from aws api endpoint"""

    url = urlopen(AWS_PRICING_INDEX)
    if not check_etags(PRICE_INDEX, url.headers["ETag"]):
        LOG.debug("fetching %s from %s", PRICE_INDEX, AWS_PRICING_INDEX)
        urlretrieve(AWS_PRICING_INDEX, CACHE_DIR + PRICE_INDEX)

    index_file = load_json(CACHE_DIR + PRICE_INDEX)

    for offer in index_file["offers"]:
        location = index_file["offers"][offer]["currentVersionUrl"]
        filename = offer + ".json"

        url = urlopen(AWS_API_ENDPOINT + location)
        if not check_etags(filename, url.headers["ETag"]):
            LOG.debug("fetching %s from %s", filename, AWS_API_ENDPOINT + location)
            urlretrieve(AWS_API_ENDPOINT + location, CACHE_DIR + filename)


def check_etags(filename, etag):
    """compare etags retrieved from api endpoint with cached etags
    param: filename of json etag cache
    param: etag to be compared
    return: boolean
    """
    etag_file = load_json(CACHE_DIR + "/etags.json")

    if filename in etag_file.keys():
        if etag == etag_file[filename]:
            LOG.debug("%s: etags match!", filename)
            return True

    LOG.debug("%s: etags do NOT match!", filename)
    etag_file[filename] = etag
    save_json(CACHE_DIR + "etags.json", etag_file)
    return False


def main():
    """main entry point"""

    if os.path.isdir(CACHE_DIR):
        try:
            delta = datetime.now() - datetime.fromtimestamp(os.path.getmtime(CACHE_DIR + PRICE_INDEX))
            if delta.days > 1 or os.path.getsize(CACHE_DIR + PRICE_INDEX) == 0:
                collect_data()
            else:
                LOG.error("Data has been downloaded recently. Skipping download...")

        except OSError as exc:
            LOG.error(exc)
    else:
        os.mkdir(CACHE_DIR)
        collect_data()


if "__main__" in __name__:
    try:
        main()
    except KeyboardInterrupt:
        print("Ctrl+C detected. Exiting...")
