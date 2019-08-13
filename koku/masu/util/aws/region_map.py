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
"""Extracts information from AWS Regions And Endpoints page."""

import json
import logging
import re

import bs4
import requests

LOG = logging.getLogger(__name__)
URL = 'https://docs.aws.amazon.com/general/latest/gr/rande.html'


def update_region_mapping():
    """Update the RegionMapping table with new data."""
    from django.db import IntegrityError
    from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor

    data = json.loads(parse_page())
    mapped = get_region_map(data)

    with ReportingCommonDBAccessor() as accessor:
        for key, val in mapped.items():
            try:
                accessor.add('region_mapping', {'region': key, 'region_name': val})
            except IntegrityError:
                warn_msg = f'Duplicate entry in DB: "{key}" - "{val}"'
                LOG.warning(warn_msg)
        accessor.commit()
    return True


def get_region_map(data):
    """Scan the parsed document to return regions and region names.

    Args: data (dict)
    Returns: a set of (region, region_name) tuples.

    """
    region_map = dict()
    for val in data.values():
        for item in val:
            if 'Region' in item.keys() and 'Region Name' in item.keys():
                region = _filter_region_string(item.get('Region'))
                region_name = _filter_region_string(item.get('Region Name'))

                if region and region_name:
                    region_map[region] = region_name
    return region_map


def _filter_region_string(string):
    """Transform strings for edge cases."""
    blacklist = ['--Global--', 'n/a']
    strip_chars = '* '

    if not string or string in blacklist:
        return None

    return string.strip(strip_chars)


def map_table(table):
    """Map an HTML table into a dict."""
    headers = []
    results = []

    for row in table.find_all(re.compile('tr')):
        for header in row.find_all(re.compile('^th')):
            headers.append(header.string)

        row_map = {}
        for i, cell in enumerate(row.find_all('td')):
            row_map[headers[i]] = cell.string

        if row_map:
            results.append(row_map)

    return results


def parse_page():
    """Parse the AWS Regions and Endpoints page into a JSON object."""
    resp = requests.get(URL, headers={'Accept-Encoding': 'UTF-8'})

    if resp.status_code != 200:
        msg = f'Unable to retrieve {URL}: {resp}'
        LOG.error(msg)
        raise IOError(msg)

    soup = bs4.BeautifulSoup(resp.text, 'html.parser')

    data = {}
    for element in soup.find_all('h2', id=re.compile(r'_region')):
        service_name = element.text

        for sib in element.next_siblings:
            # limit traversal, don't overlap the next sibling
            if isinstance(sib, bs4.element.Tag) and sib.name == 'h2':
                break

            if isinstance(sib, bs4.element.Tag) and sib.name == 'div':
                selected = sib.select('div > table')
                if selected:
                    table = map_table(selected.pop())
                    data[service_name] = table

            if isinstance(sib, bs4.element.Tag) and sib.name == 'p' and \
                    re.search('single endpoint', str(sib)):
                data[service_name] = [{'Endpoint': sib.string.strip()}]

    dbg_msg = f'Parsed AWS Endpoints page: {data}'
    LOG.debug(dbg_msg)
    return json.dumps(data)
