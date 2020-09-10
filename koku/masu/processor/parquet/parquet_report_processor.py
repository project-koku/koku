#
# Copyright 2020 Red Hat, Inc.
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
"""Processor to convert Cost Usage Reports to parquet."""


class ParquetReportProcessor:
    """Parquet report processor."""

    def __init__(self, schema_name, report_path, compression, provider_uuid, manifest_id=None):
        """initialize report processor."""
        self._schema_name = schema_name
        self._provider_uuid = provider_uuid
        self._report_file = report_path
        self._manifest_id = manifest_id

    def process(self):
        """Convert to parquet."""
        pass

    def remove_temp_cur_files(self, report_path):
        """Remove processed files."""
        pass
