import logging
import os

import pandas as pd

from api.common import log_json
from masu.util.aws.common import copy_local_report_file_to_s3_bucket

LOG = logging.getLogger(__name__)


class CSVFileHandler:
    """Class to handle csv files and S3 Object Storage."""

    def __init__(self, schema_name, provider, provider_uuid):
        """Establish parquet summary processor."""
        self._schema_name = schema_name
        self._provider = provider
        self._provider_uuid = provider_uuid

    def write_csv_to_s3(self, date, data, tracing_id=None):
        """
        Generates an HCS CSV from the specified schema and provider.
        :param date
        :param data
        :param tracing_id

        :return none
        """

        LOG.info(log_json(tracing_id, "preparing to write file to object storage"))
        my_df = pd.DataFrame(data)
        filename = f"hcs_test_csv_{date}.csv"
        my_df.to_csv(filename, index=False)
        s3_csv_path = f"hcs/{self._schema_name}/{self._provider}/{self._provider_uuid}"
        copy_local_report_file_to_s3_bucket(tracing_id, s3_csv_path, filename, filename, "", date)
        os.remove(filename)
