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

"""Test the Kafka msg handler."""

import json
import os
import shutil
import tempfile
from unittest.mock import patch

import requests_mock
from requests.exceptions import HTTPError

import masu.external.kafka_msg_handler as msg_handler
from api.models import Provider
from masu.config import Config
from masu.external.accounts_accessor import AccountsAccessor, AccountsAccessorError
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase


class KafkaMsg:
    """A Kafka Message."""

    def __init__(self, topic, url):
        """Initialize a Kafka Message."""
        self.topic = topic
        value_dict = {'url': url}
        value_str = json.dumps(value_dict)
        self.value = value_str.encode('utf-8')


class KafkaMsgHandlerTest(MasuTestCase):
    """Test Cases for the Kafka msg handler."""

    def setUp(self):
        """Set up each test case."""
        super().setUp()
        payload_file = open('./koku/masu/test/data/ocp/payload.tar.gz', 'rb')
        bad_payload_file = open('./koku/masu/test/data/ocp/bad_payload.tar.gz', 'rb')
        self.tarball_file = payload_file.read()
        payload_file.close()

        self.bad_tarball_file = bad_payload_file.read()
        bad_payload_file.close()

        self.cluster_id = 'my-ocp-cluster-1'
        self.date_range = '20190201-20190301'

    def test_extract_payload(self):
        """Test to verify extracting payload is successful."""
        payload_url = 'http://insights-upload.com/quarnantine/file_to_validate'
        with requests_mock.mock() as m:
            m.get(payload_url, content=self.tarball_file)

            fake_dir = tempfile.mkdtemp()
            fake_pvc_dir = tempfile.mkdtemp()
            with patch.object(Config, 'INSIGHTS_LOCAL_REPORT_DIR', fake_dir):
                with patch.object(Config, 'TMP_DIR', fake_dir):
                    msg_handler.extract_payload(payload_url)
                    expected_path = '{}/{}/{}/'.format(
                        Config.INSIGHTS_LOCAL_REPORT_DIR, self.cluster_id, self.date_range,
                    )
                    self.assertTrue(os.path.isdir(expected_path))
                    shutil.rmtree(fake_dir)
                    shutil.rmtree(fake_pvc_dir)

    def test_extract_bad_payload(self):
        """Test to verify extracting payload missing report files is not successful."""
        payload_url = 'http://insights-upload.com/quarnantine/file_to_validate'
        with requests_mock.mock() as m:
            m.get(payload_url, content=self.bad_tarball_file)

            fake_dir = tempfile.mkdtemp()
            fake_pvc_dir = tempfile.mkdtemp()
            with patch.object(Config, 'INSIGHTS_LOCAL_REPORT_DIR', fake_dir):
                with patch.object(Config, 'TMP_DIR', fake_dir):
                    with self.assertRaises(msg_handler.KafkaMsgHandlerError):
                        msg_handler.extract_payload(payload_url)
                    shutil.rmtree(fake_dir)
                    shutil.rmtree(fake_pvc_dir)

    def test_extract_payload_bad_url(self):
        """Test to verify extracting payload exceptions are handled."""
        payload_url = 'http://insights-upload.com/quarnantine/file_to_validate'

        with requests_mock.mock() as m:
            m.get(payload_url, exc=HTTPError)

            with self.assertRaises(msg_handler.KafkaMsgHandlerError):
                msg_handler.extract_payload(payload_url)

    def test_extract_payload_unable_to_open(self):
        """Test to verify extracting payload exceptions are handled."""
        payload_url = 'http://insights-upload.com/quarnantine/file_to_validate'

        with requests_mock.mock() as m:
            m.get(payload_url, content=self.tarball_file)
            with patch('masu.external.kafka_msg_handler.open') as mock_oserror:
                mock_oserror.side_effect = PermissionError
                with self.assertRaises(msg_handler.KafkaMsgHandlerError):
                    msg_handler.extract_payload(payload_url)

    def test_extract_payload_wrong_file_type(self):
        """Test to verify extracting payload is successful."""
        payload_url = 'http://insights-upload.com/quarnantine/file_to_validate'

        with requests_mock.mock() as m:
            payload_file = open('./koku/masu/test/data/test_cur.csv', 'rb')
            csv_file = payload_file.read()
            payload_file.close()

            m.get(payload_url, content=csv_file)

            with self.assertRaises(msg_handler.KafkaMsgHandlerError):
                msg_handler.extract_payload(payload_url)

    def test_handle_messages(self):
        """Test to ensure that kafka messages are handled."""
        hccm_msg = KafkaMsg(
            msg_handler.HCCM_TOPIC, 'http://insights-upload.com/quarnantine/file_to_validate',
        )
        advisor_msg = KafkaMsg(
            'platform.upload.advisor', 'http://insights-upload.com/quarnantine/file_to_validate',
        )

        # Verify that when extract_payload is successful with 'hccm' message that SUCCESS_CONFIRM_STATUS is returned
        with patch('masu.external.kafka_msg_handler.extract_payload', return_value=None):
            self.assertEqual(
                msg_handler.handle_message(hccm_msg), (msg_handler.SUCCESS_CONFIRM_STATUS, None),
            )

        # Verify that when extract_payload is not successful with 'hccm' message that FAILURE_CONFIRM_STATUS is returned
        with patch(
            'masu.external.kafka_msg_handler.extract_payload',
            side_effect=msg_handler.KafkaMsgHandlerError,
        ):
            self.assertEqual(
                msg_handler.handle_message(hccm_msg), (msg_handler.FAILURE_CONFIRM_STATUS, None),
            )

        # Verify that when None status is returned for non-hccm messages (we don't confirm these)
        self.assertEqual(msg_handler.handle_message(advisor_msg), (None, None))

    def test_get_account(self):
        """Test that the account details are returned given a provider uuid."""
        ocp_account = msg_handler.get_account(self.ocp_test_provider_uuid)
        self.assertIsNotNone(ocp_account)
        self.assertEqual(ocp_account.get('provider_type'), Provider.PROVIDER_OCP)

    @patch.object(AccountsAccessor, 'get_accounts')
    def test_get_account_exception(self, mock_accessor):
        """Test that no account is returned upon exception."""
        mock_accessor.side_effect = AccountsAccessorError('Sample timeout error')
        ocp_account = msg_handler.get_account(self.ocp_test_provider_uuid)
        self.assertIsNone(ocp_account)

    @patch('masu.external.kafka_msg_handler.summarize_reports')
    @patch('masu.external.kafka_msg_handler.get_report_files')
    def test_process_report_unknown_cluster_id(self, mock_get_reports, mock_summarize):
        """Test processing a report for an unknown cluster_id."""
        mock_download_process_value = [
            {
                'schema_name': self.schema,
                'provider_type': Provider.PROVIDER_OCP,
                'provider_uuid': self.ocp_test_provider_uuid,
                'start_date': DateAccessor().today(),
            }
        ]
        mock_get_reports.return_value = mock_download_process_value
        sample_report = {'cluster_id': 'missing_cluster_id'}

        msg_handler.process_report(sample_report)

        mock_summarize.delay.assert_not_called()

    @patch('masu.external.kafka_msg_handler.summarize_reports')
    @patch('masu.external.kafka_msg_handler.get_report_files')
    def test_process_report(self, mock_get_reports, mock_summarize):
        """Test processing a report for an unknown cluster_id."""
        mock_download_process_value = [
            {
                'schema_name': self.schema,
                'provider_type': Provider.PROVIDER_OCP,
                'provider_uuid': self.ocp_test_provider_uuid,
                'start_date': DateAccessor().today(),
            }
        ]
        mock_get_reports.return_value = mock_download_process_value
        cluster_id = self.ocp_provider_resource_name
        sample_report = {'cluster_id': cluster_id, 'date': DateAccessor().today()}

        msg_handler.process_report(sample_report)

        mock_summarize.delay.assert_called_with(mock_download_process_value)

    @patch('masu.external.kafka_msg_handler.summarize_reports')
    @patch('masu.external.kafka_msg_handler.get_report_files')
    def test_process_report_inactive_provider(self, mock_get_reports, mock_summarize):
        """Test processing a report for an inactive provider."""
        self.ocp_provider.active = False
        self.ocp_provider.save()

        mock_download_process_value = [
            {
                'schema_name': self.schema,
                'provider_type': Provider.PROVIDER_OCP,
                'provider_uuid': self.ocp_test_provider_uuid,
                'start_date': DateAccessor().today(),
            }
        ]
        mock_get_reports.return_value = mock_download_process_value
        cluster_id = self.ocp_provider_resource_name
        sample_report = {'cluster_id': cluster_id, 'date': DateAccessor().today()}

        msg_handler.process_report(sample_report)

        mock_summarize.delay.assert_not_called()
