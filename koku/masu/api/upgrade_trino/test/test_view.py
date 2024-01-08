#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the verify parquet files endpoint view."""
import datetime
from unittest.mock import patch
from uuid import uuid4

from django.test.utils import override_settings
from django.urls import reverse

from api.models import Provider
from masu.api.upgrade_trino.util.task_handler import FixParquetTaskHandler
from masu.processor.tasks import GET_REPORT_FILES_QUEUE
from masu.test import MasuTestCase


@override_settings(ROOT_URLCONF="masu.urls")
class TestUpgradeTrinoView(MasuTestCase):
    ENDPOINT = "fix_parquet"
    bill_date = datetime.datetime(2024, 1, 1, 0, 0)

    @patch("koku.middleware.MASU", return_value=True)
    def test_required_parameters_failure(self, _):
        """Test the hcs_report_finalization endpoint."""
        parameter_options = [{}, {"start_date": self.bill_date}, {"provider_uuid": self.aws_provider_uuid}]
        for parameters in parameter_options:
            with self.subTest(parameters=parameters):
                response = self.client.get(reverse(self.ENDPOINT), parameters)
                self.assertEqual(response.status_code, 400)

    @patch("koku.middleware.MASU", return_value=True)
    def test_provider_uuid_does_not_exist(self, _):
        """Test the hcs_report_finalization endpoint."""
        parameters = {"start_date": self.bill_date, "provider_uuid": str(uuid4())}
        response = self.client.get(reverse(self.ENDPOINT), parameters)
        self.assertEqual(response.status_code, 400)

    @patch("koku.middleware.MASU", return_value=True)
    def test_acceptable_parameters(self, _):
        """Test that the endpoint accepts"""
        acceptable_parameters = [
            {"start_date": self.bill_date, "provider_uuid": self.aws_provider_uuid, "simulate": True},
            {"start_date": self.bill_date, "provider_uuid": self.aws_provider_uuid, "simulate": "bad_value"},
            {"start_date": self.bill_date, "provider_type": self.aws_provider.type},
        ]
        cleaned_column_mapping = FixParquetTaskHandler.clean_column_names(self.aws_provider.type)
        for parameters in acceptable_parameters:
            with self.subTest(parameters=parameters):
                with patch("masu.celery.tasks.fix_parquet_data_types.apply_async") as patch_celery:
                    response = self.client.get(reverse(self.ENDPOINT), parameters)
                    self.assertEqual(response.status_code, 200)
                    simulate = parameters.get("simulate", False)
                    if simulate == "bad_value":
                        simulate = False
                    async_kwargs = {
                        "schema_name": self.schema_name,
                        "provider_type": Provider.PROVIDER_AWS_LOCAL,
                        "provider_uuid": self.aws_provider.uuid,
                        "simulate": simulate,
                        "bill_date": self.bill_date,
                        "cleaned_column_mapping": cleaned_column_mapping,
                    }
                    patch_celery.assert_called_once_with((), async_kwargs, queue=GET_REPORT_FILES_QUEUE)
