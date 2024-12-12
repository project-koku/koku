"""Upload utility functions."""

from django.conf import settings

_DB_FETCH_BATCH_SIZE = 2000


def get_upload_path(schema_name, provider_type, provider_uuid, date, table_name, daily=False):
    """
    Get the s3 upload_path for a file.

    Args:
        schema_name (str): Koku user account (schema) name.
        provider_type (str): Koku backend provider type identifier.
        provider_uuid (UUID): Koku backend provider UUID.
        date (date): Date at which the exported data is relevant.
        table_name (str): Name of the table being exported.
        daily (bool): If true, include the day of month in the path.

    Returns:
        upload_path (str): Path that file should be stored at in S3.

    """
    if daily:
        date_part = f"{date.year}/{date.month:02d}/{date.day:02d}"
    else:
        # Note: "00" is a magic path segment we use to indicate files that
        # are relevant to the month but not to a specific day in that month.
        date_part = f"{date.year}/{date.month:02d}/00"
    upload_path = (
        f"{settings.S3_BUCKET_PATH}/{schema_name}/{provider_type}/{provider_uuid}/" f"{date_part}/{table_name}.csv.gz"
    )
    return upload_path
