#
# Copyright 2018 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Downloader for cost usage reports."""

from masu.database.koku_database_access import KokuDBAccess
from masu.external.date_accessor import DateAccessor


class ReportStatsDBAccessor(KokuDBAccess):
    """Class to interact with the koku database for CUR processing statistics."""

    def __init__(self, report_name, manifest_id, schema='public'):
        """
        Establish CUR statistics database connection.

        Args:
            report_name    (String) CUR report file name
            provider_id    (String) the database id of the provider
            schema         (String) database schema (i.e. public or customer tenant value)
        """
        super().__init__(schema)
        self._manifest_id = manifest_id
        self._report_name = report_name
        self._costentrystatus = self.get_base().classes.reporting_common_costusagereportstatus

        if self.does_db_entry_exist() is False:
            update_fields = {}
            update_fields['report_name'] = self._report_name
            update_fields['manifest_id'] = self._manifest_id
            self.add(update_fields)

        self._obj = self._get_db_obj_query().first()

    def _get_db_obj_query(self):
        """
        Return the sqlachemy query for the report stats object.

        Args:
            None
        Returns:
            (sqlalchemy.orm.query.Query): "SELECT public.api_customer.group_ptr_id ..."
        """
        obj = self._session.query(self._costentrystatus).filter_by(report_name=self._report_name)
        return obj

    def commit(self):
        """
        Commit pending database changes.

        Args:
            None
        Returns:
            None
        """
        self._session.commit()

    def get_cursor_position(self):
        """
        Return current cursor position for processing CUR.

        Args:
            None
        Returns:
            (Integer): last byte offset for the given CUR file.
        """
        return self._obj.cursor_position

    def set_cursor_position(self, new_position):
        """
        Save current cursor position for processing CUR.

        Args:
            new_position (Integer): last byte offset for the given CUR file.
        Returns:
            None

        """
        self._obj.cursor_position = new_position

    def get_last_completed_datetime(self):
        """
        Getter for last_completed_datetime.

        Args:
            None
        Returns:
            (DateTime): Time stamp for last completed date/time.
        """
        return self._obj.last_completed_datetime

    def get_last_started_datetime(self):
        """
        Getter for last_started_datetime.

        Args:
            None
        Returns:
            (DateTime): Time stamp for last started date/time.
        """
        return self._obj.last_started_datetime

    def log_last_started_datetime(self):
        """
        Convinence method for logging start processing.

        Args:
            None
        Returns:
            None
        """
        self._obj.last_started_datetime = DateAccessor().today_with_timezone('UTC')

    def log_last_completed_datetime(self):
        """
        Convinence method for logging processing completed.

        Args:
            None
        Returns:
            None
        """
        self._obj.last_completed_datetime = DateAccessor().today_with_timezone('UTC')

    def get_etag(self):
        """
        Getter for the report file's etag.

        Args:
            None
        Returns:
            last_completed_datetime (String): MD5 hash of object.
        """
        return self._obj.etag

    def add(self, fields_dict):
        """
        Add a new row to the CUR stats database.

        Args:
            (Dictionary): Fields containing CUR Status attributes.

            Valid keys are: report_name,
                            manifest_id,
                            last_completed_date (optional),
                            last_started_date (optional),
                            etag (optional)
        Returns:
            None

        """
        new_entry = self._costentrystatus(**fields_dict)
        self._session.add(new_entry)

    def remove(self):
        """
        Remove a CUR statistics from the database.

        Args:
            None
        Returns:
            None
        """
        self._session.delete(self._obj)

    def update(self,
               cursor_position=None,
               last_completed_datetime=None,
               last_started_datetime=None,
               etag=None):
        """
        Update a CUR statistics record in the database.

        Args:
            cursor_position (Integer): Byte offset of the last position processed in a CUR
            last_completed_datetime (DateTime): Timestamp for the time processing completed.
            last_started_datetime (DateTime): Timestamp for the time processing started.
            etag (String): MD5 hash of the CUR file.

        Returns:
            None

        """
        obj_to_update = self._obj
        if cursor_position:
            obj_to_update.cursor_position = cursor_position
        if last_completed_datetime:
            obj_to_update.last_completed_datetime = last_completed_datetime
        if last_started_datetime:
            obj_to_update.last_started_datetime = last_started_datetime
        if etag:
            obj_to_update.etag = etag
