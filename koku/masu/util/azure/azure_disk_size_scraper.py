import logging

import requests
from bs4 import BeautifulSoup

LOG = logging.getLogger(__name__)


class AzureDiskSizeScraper:
    def __init__(self):
        self.url = "https://azure.microsoft.com/en-us/pricing/details/managed-disks/"
        self.fetch_data = {}

    @staticmethod
    def format_disk_size(dis_size_str):
        """Formats the string found for the disk size"""
        gib = "GiB"
        tib = "TiB"
        size_list = dis_size_str.split(" ")
        if len(size_list) < 2:
            # Skip anything not in "int unit" format
            return None
        size = size_list[0]
        unit = size_list[1]
        if gib not in unit and tib not in unit:
            return None
        try:
            if tib in unit:
                return int(size) * 1024
            elif unit == gib:
                return int(size)
            else:
                LOG.error(f"Unrecognized unit: {unit}")
        except Exception:
            LOG.info("Unexpected error formatting disk size")
            return None

    def scrape_disk_size(self):
        try:
            response = requests.get(self.url)
            response.raise_for_status()
            page_content = response.text
        except requests.exceptions.RequestException as e:
            LOG.error(f"Unable to retrieve azure disk capacities: {e}")
            return

        soup = BeautifulSoup(page_content, "html.parser")
        tables = soup.find_all("table")
        for table in tables:
            headers = table.find_all("th")
            for header in headers:
                if "Disk Size" in header.get_text(strip=True):
                    rows = table.find_all("tr")
                    for row in rows:
                        cells = row.find_all("td")
                        cell_data = [cell.get_text(strip=True) for cell in cells]
                        if cell_data:
                            sku_prefix = cell_data[0]
                            if disk_size := self.format_disk_size(cell_data[1]):
                                self.fetch_data[sku_prefix] = disk_size
        return self.fetch_data
