"""Upload utility functions."""
import csv

from django.conf import settings
from django.db import connection

from api.dataexport.uploader import AwsS3Uploader
from masu.util.common import NamedTemporaryGZip


def get_upload_path(account_name, provider_type, date, table_name):
    """Get the s3 upload_path for a file."""
    upload_path = (
        '{bucket_path}/{account_name}/{provider_type}/'
        '{year}/{month:02d}/{table_name}.csv.gz'.format(
            bucket_path=settings.S3_BUCKET_PATH,
            account_name=account_name,
            provider_type=provider_type,
            year=date.year,
            month=date.month,
            table_name=table_name,
        )
    )
    return upload_path


def query_and_upload_to_s3(schema, table, date_range):
    """Query the database and upload the results to s3."""
    uploader = AwsS3Uploader(settings.S3_BUCKET_NAME)

    with connection.cursor() as cursor:
        cursor.db.set_schema(schema)
        upload_path = get_upload_path(
            schema, table.provider, date_range[0], table.table_name
        )
        cursor.execute(
            table.sql.format(schema=schema),
            {'start_date': date_range[0], 'end_date': date_range[1]},
        )
        # Don't upload if result set is empty
        if cursor.rowcount == 0:
            return

        with NamedTemporaryGZip() as temp_file:
            writer = csv.writer(
                temp_file,
                quotechar='"',
                quoting=csv.QUOTE_MINIMAL
            )
            writer.writerow([field.name for field in cursor.description])
            for row in cursor.fetchall():
                writer.writerow(row)
            temp_file.close()
            uploader.upload_file(temp_file.name, upload_path)
