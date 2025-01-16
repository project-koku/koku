import logging
import os

import pandas as pd
from botocore.exceptions import ClientError
from botocore.exceptions import EndpointConnectionError
from dateutil import relativedelta
from django.conf import settings

from api.common import log_json
from masu.util.aws.common import get_s3_resource

LOG = logging.getLogger(__name__)


class CSVFileHandler:
    """Class to handle csv files and S3 Object Storage."""

    def __init__(self, schema_name, provider, provider_uuid):
        """Establish parquet summary processor."""
        self._schema_name = str(schema_name).strip("acct")
        self._provider = provider
        self._provider_uuid = provider_uuid
        self._s3_resource = get_s3_resource(
            access_key=settings.S3_HCS_ACCESS_KEY,
            secret_key=settings.S3_HCS_SECRET,
            region=settings.S3_HCS_REGION,
            endpoint_url=settings.S3_HCS_ENDPOINT,
        )

    def write_csv_to_s3(self, date, data, cols, finalize=False, tracing_id=None):
        """
        Generates an HCS CSV from the specified schema and provider.
        :param date
        :param data
        :param cols
        :param finalize
        :param tracing_id

        :return none
        """
        filename = f"hcs_{date}.csv"
        month = date.strftime("%m")
        year = date.strftime("%Y")
        context = {
            "provider_uuid": self._provider_uuid,
            "provider_type": self._provider,
            "schema": self._schema_name,
            "date": date,
        }
        finalize_date = None
        if finalize:
            # reports are finalized on the 15th of the month following the report date
            finalize_date = (date.replace(day=15) + relativedelta.relativedelta(months=1)).strftime("%Y-%m-%d")
        s3_path = (
            f"hcs/csv/{self._schema_name}/{self._provider}/source={self._provider_uuid}/year={year}/month={month}"
        )

        LOG.info(log_json(tracing_id, msg="preparing to write file to object storage", context=context))
        self.copy_data_to_s3_bucket(tracing_id, data, cols, filename, s3_path, finalize, finalize_date, context)
        LOG.info(log_json(tracing_id, msg="wrote file to object storage", context=context))

    def copy_data_to_s3_bucket(
        self, tracing_id, data, cols, filename, s3_path, finalize, finalize_date, context
    ):  # pragma: no cover
        """Copy hcs data to S3 bucket."""
        my_df = pd.DataFrame(data)
        my_df.to_csv(filename, header=cols, index=False)
        metadata = {"finalized": str(finalize)}
        if finalize and finalize_date:
            metadata["finalized-date"] = finalize_date
        extra_args = {"Metadata": metadata}
        with open(filename, "rb") as fin:
            try:
                upload_key = f"{s3_path}/{filename}"
                s3_obj = {"bucket_name": settings.S3_HCS_BUCKET_NAME, "key": upload_key}
                upload = self._s3_resource.Object(**s3_obj)
                upload.upload_fileobj(fin, ExtraArgs=extra_args)
            except (EndpointConnectionError, ClientError) as err:
                msg = f"unable to copy data to {upload_key}, bucket {settings.S3_HCS_BUCKET_NAME}. Reason: {str(err)}"
                LOG.warning(log_json(tracing_id, msg=msg, context=context))
                return
        os.remove(filename)
