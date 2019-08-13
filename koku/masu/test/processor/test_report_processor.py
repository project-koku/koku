#
# Copyright 2018 Red Hat, Inc.
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

"""Test the ReportProcessor object."""

from datetime import datetime
from unittest.mock import patch

from masu.exceptions import MasuProcessingError
from masu.external import (
    AMAZON_WEB_SERVICES,
    AWS_LOCAL_SERVICE_PROVIDER,
    OPENSHIFT_CONTAINER_PLATFORM,
    OCP_LOCAL_SERVICE_PROVIDER,
)
from masu.processor.report_processor import ReportProcessor, ReportProcessorError
from masu.processor.aws.aws_report_processor import AWSReportProcessor
from masu.processor.ocp.ocp_report_processor import OCPReportProcessor

from masu.test import MasuTestCase
from masu.test.external.downloader.aws import fake_arn


class ReportProcessorTest(MasuTestCase):
    """Test Cases for the ReportProcessor object."""

    def test_initializer_aws(self):
        """Test to initializer for AWS"""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path='/my/report/file',
            compression='GZIP',
            provider=AMAZON_WEB_SERVICES,
            provider_id=self.aws_provider.id,
            manifest_id=None,
        )
        self.assertIsNotNone(processor._processor)

    def test_initializer_aws_local(self):
        """Test to initializer for AWS-local"""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path='/my/report/file',
            compression='GZIP',
            provider=AWS_LOCAL_SERVICE_PROVIDER,
            provider_id=self.aws_provider.id,
            manifest_id=None,
        )
        self.assertIsNotNone(processor._processor)

    def test_initializer_ocp(self):
        """Test to initializer for OCP"""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path='./koku/masu/test/data/ocp/e6b3701e-1e91-433b-b238-a31e49937558_February-2019-my-ocp-cluster-1.csv',
            compression='PLAIN',
            provider=OPENSHIFT_CONTAINER_PLATFORM,
            provider_id=self.aws_provider.id,
            manifest_id=None,
        )
        self.assertIsNotNone(processor._processor)

    def test_initializer_ocp_local(self):
        """Test to initializer for OCP-local"""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path='./koku/masu/test/data/ocp/e6b3701e-1e91-433b-b238-a31e49937558_February-2019-my-ocp-cluster-1.csv',
            compression='PLAIN',
            provider=OCP_LOCAL_SERVICE_PROVIDER,
            provider_id=self.aws_provider.id,
            manifest_id=None,
        )
        self.assertIsNotNone(processor._processor)

    @patch(
        'masu.processor.aws.aws_report_processor.AWSReportProcessor.__init__',
        side_effect=MasuProcessingError,
    )
    def test_initializer_error(self, fake_processor):
        """Test to initializer with error."""
        with self.assertRaises(ReportProcessorError):
            ReportProcessor(
                schema_name=self.schema,
                report_path='/my/report/file',
                compression='GZIP',
                provider=AMAZON_WEB_SERVICES,
                provider_id=self.aws_provider.id,
                manifest_id=None,
            )

    def test_initializer_invalid_provider(self):
        """Test to initializer with invalid provider"""
        with self.assertRaises(ReportProcessorError):
            ReportProcessor(
                schema_name=self.schema,
                report_path='/my/report/file',
                compression='GZIP',
                provider='unknown',
                provider_id=self.aws_provider.id,
                manifest_id=None,
            )

    @patch(
        'masu.processor.aws.aws_report_processor.AWSReportProcessor.process',
        return_value=None,
    )
    def test_aws_process(self, fake_process):
        """Test to process for AWS"""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path='/my/report/file',
            compression='GZIP',
            provider=AMAZON_WEB_SERVICES,
            provider_id=self.aws_provider.id,
            manifest_id=None,
        )
        try:
            processor.process()
        except Exception:
            self.fail('unexpected error')

    @patch(
        'masu.processor.aws.aws_report_processor.AWSReportProcessor.process',
        side_effect=MasuProcessingError,
    )
    def test_aws_process_error(self, fake_process):
        """Test to process for AWS with processing error"""

        processor = ReportProcessor(
            schema_name=self.schema,
            report_path='/my/report/file',
            compression='GZIP',
            provider=AMAZON_WEB_SERVICES,
            provider_id=self.aws_provider.id,
            manifest_id=None,
        )
        with self.assertRaises(ReportProcessorError):
            processor.process()

    @patch(
        'masu.processor.aws.aws_report_processor.AWSReportProcessor.remove_temp_cur_files',
        return_value=None,
    )
    def test_aws_remove_processed_files(self, fake_process):
        """Test to remove_processed_files for AWS"""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path='/my/report/file',
            compression='GZIP',
            provider=AMAZON_WEB_SERVICES,
            provider_id=self.aws_provider.id,
            manifest_id=None,
        )
        try:
            processor.remove_processed_files('/my/report/file')
        except Exception:
            self.fail('unexpected error')

    @patch(
        'masu.processor.aws.aws_report_processor.AWSReportProcessor.remove_temp_cur_files',
        side_effect=MasuProcessingError,
    )
    def test_aws_remove_processed_files_error(self, fake_process):
        """Test to remove_processed_files for AWS with processing error"""

        processor = ReportProcessor(
            schema_name=self.schema,
            report_path='/my/report/file',
            compression='GZIP',
            provider=AMAZON_WEB_SERVICES,
            provider_id=self.aws_provider.id,
            manifest_id=None,
        )
        with self.assertRaises(ReportProcessorError):
            processor.remove_processed_files('/my/report/file')
