"""Upload utility functions."""
import csv

from dateutil.rrule import DAILY, rrule
from django.conf import settings
from django.db import connection

from api.dataexport.uploader import AwsS3Uploader
from masu.util.common import NamedTemporaryGZip


def get_upload_path(account_name, provider_type, date, table_name, daily=False):
    """
    Get the s3 upload_path for a file.

    Args:
        account_name (str): Koku user account (schema) name.
        provider_type (str): Koku backend provider type identifier.
        date (date): Date at which the exported data is relevant.
        table_name (str): Name of the table being exported.
        daily (bool): If true, include the day of month in the path.

    Returns:
        upload_path (str): Path that file should be stored at in S3.

    """
    if daily:
        date_part = '{year}/{month:02d}/{day:02d}'.format(
            year=date.year, month=date.month, day=date.day
        )
    else:
        # Note: "00" is a magic path segment we use to indicate files that
        # are relevant to the month but not to a specific day in that month.
        date_part = '{year}/{month:02d}/00'.format(year=date.year, month=date.month)
    upload_path = (
        '{bucket_path}/{account_name}/{provider_type}/'
        '{date_part}/{table_name}.csv.gz'.format(
            bucket_path=settings.S3_BUCKET_PATH,
            account_name=account_name,
            provider_type=provider_type,
            date_part=date_part,
            table_name=table_name,
        )
    )
    return upload_path


def query_and_upload_to_s3(schema, table_export_setting, date_range):
    """
    Query the database and upload the results to s3.

    Args:
        schema (str): Account schema name in which to execute the query.
        table_export_setting (TableExportSetting): Settings for the table export.
        date_range (tuple): Pair of date objects of inclusive start and end dates.

    """
    uploader = AwsS3Uploader(settings.S3_BUCKET_NAME)
    start_date, end_date = date_range
    iterate_daily = table_export_setting.iterate_daily
    dates_to_iterate = rrule(
        DAILY, dtstart=start_date, until=end_date if iterate_daily else start_date
    )

    with connection.cursor() as cursor:
        cursor.db.set_schema(schema)
        for the_date in dates_to_iterate:
            upload_path = get_upload_path(
                schema,
                table_export_setting.provider,
                the_date,
                table_export_setting.output_name,
                iterate_daily,
            )
            cursor.execute(
                table_export_setting.sql.format(schema=schema),
                {
                    'start_date': the_date,
                    'end_date': the_date if iterate_daily else end_date,
                },
            )
            # Don't upload if result set is empty
            if cursor.rowcount == 0:
                return
            with NamedTemporaryGZip() as temp_file:
                writer = csv.writer(temp_file, quotechar='"', quoting=csv.QUOTE_MINIMAL)
                writer.writerow([field.name for field in cursor.description])
                for row in cursor.fetchall():
                    writer.writerow(row)
                uploader.upload_file(temp_file.name, upload_path)
