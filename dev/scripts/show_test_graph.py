#!/usr/bin/python3
#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""draw a graph from cost & forecast data."""
import datetime
import json
import sys
from pprint import pformat

import matplotlib as mlt
import matplotlib.pyplot as plt
import requests
from requests.exceptions import HTTPError

FORECAST_URL = "http://localhost:8000/api/cost-management/v1/forecasts/aws/costs/"
COST_URL = "http://localhost:8000/api/cost-management/v1/reports/aws/costs/"


def _get_data(url):
    response = requests.get(url)
    try:
        response.raise_for_status()
    except HTTPError as err:
        print("Error: %s" % err)

    try:
        resp = json.loads(response.content)
    except json.decoder.JSONDecodeError as exc:
        print("Error decoding API response: %s" % exc)

        from bs4 import BeautifulSoup

        errdoc = BeautifulSoup(response.content, "html.parser")
        print(errdoc.find(id="traceback_area").get_text())

        # print(response.text)
        sys.exit(1)

    # print(resp)
    return resp.get("data")


def _value(dikt, key):
    return dikt.get(key).get("value")


def _get_values(key_name, data, fields=["total"]):
    x = []
    y = []
    upper_conf_y = []
    lower_conf_y = []

    for item in data:
        for val in item.get("values"):
            date = datetime.datetime.strptime(val.get("date"), "%Y-%m-%d")
            x.append(date.timestamp())

            if "total" in fields:
                y.append(_value(val[key_name], "total"))
            if "upper_conf_y" in fields:
                upper_conf_y.append(_value(val[key_name], "confidence_max"))
            if "lower_conf_y" in fields:
                lower_conf_y.append(_value(val[key_name], "confidence_min"))

    ret = [n for n in (x, y, upper_conf_y, lower_conf_y) if n]  # don't return empty lists
    return ret


# init matplotlib
mlt.use("GTK3Agg")
fig, ax = plt.subplots()

cost_data = _get_data(COST_URL)
x, y = _get_values("cost", cost_data)

print("Cost X: %s" % x)
print("Cost Y: %s" % y)

ax.scatter(x, y, label="aws cost")

forecast_data = _get_data(FORECAST_URL)

try:
    x, y, upper, lower = _get_values("cost", forecast_data, fields=["total", "upper_conf_y", "lower_conf_y"])
except ValueError:
    print("Error: unexpected API response")
    print("Response: %s" % pformat(forecast_data))
    sys.exit(-1)

print("Forecast X: %s" % x)
print("Forecast Y: %s" % y)
print("Upper Conf.: %s" % upper)
print("Lower Conf.: %s" % lower)

ax.plot(x, y, label="forecast", color="red")
ax.plot(x, lower, label="lower conf.", color="green", linestyle="dashed")
ax.plot(x, upper, label="upper conf.", color="green", linestyle="dashed")

# general graph properties
ax.set_xlabel("time (epoch)")  # Add an x-label to the axes.
ax.set_ylabel("cost")  # Add a y-label to the axes.
ax.set_title("Test forecast")  # Add a title to the axes.
ax.legend()

plt.show()
