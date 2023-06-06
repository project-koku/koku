import logging
import os

import pandas as pd

from api.common import log_json
from masu.util.aws.common import copy_local_hcs_report_file_to_s3_bucket

LOG = logging.getLogger(__name__)


class CSVFileHandler:
    """Class to handle csv files and S3 Object Storage."""

    def __init__(self, schema_name, provider, provider_uuid):
        """Establish parquet summary processor."""
        self._schema_name = str(schema_name).strip("acct")
        self._provider = provider
        self._provider_uuid = provider_uuid

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
        my_df = pd.DataFrame(data)
        filename = f"hcs_{date}.csv"
        month = date.strftime("%m")
        year = date.strftime("%Y")
        s3_csv_path = (
            f"hcs/csv/{self._schema_name}/{self._provider}/source={self._provider_uuid}/year={year}/month={month}"
        )

        LOG.info(log_json(tracing_id, msg="preparing to write file to object storage"))
        my_df.to_csv(filename, header=cols, index=False)
        copy_local_hcs_report_file_to_s3_bucket(tracing_id, s3_csv_path, filename, filename, finalize, date)
        os.remove(filename)
