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

"""Test the Orchestrator object."""

import random
import logging

import faker
from unittest.mock import patch

from masu.external import AMAZON_WEB_SERVICES, AZURE, OPENSHIFT_CONTAINER_PLATFORM
from masu.external.accounts_accessor import AccountsAccessor, AccountsAccessorError
from masu.processor.expired_data_remover import ExpiredDataRemover
from masu.processor.orchestrator import Orchestrator
from masu.test import MasuTestCase
from masu.test.external.downloader.aws import fake_arn


class FakeDownloader:
    fake = faker.Faker()

    def download_reports(self, number_of_months=1):
        path = '/var/tmp/masu'
        fake_files = []
        for _ in range(1, random.randint(5, 50)):
            fake_files.append(
                {
                    'file': '{}/{}/aws/{}-{}.csv'.format(
                        path, self.fake.word(), self.fake.word(), self.fake.word()
                    ),
                    'compression': random.choice(['GZIP', 'PLAIN']),
                }
            )
        return fake_files


class OrchestratorTest(MasuTestCase):
    """Test Cases for the Orchestrator object."""

    fake = faker.Faker()

    def setUp(self):
        super().setUp()
        self.mock_accounts = []
        for _ in range(1, random.randint(5, 20)):
            self.mock_accounts.append(
                {
                    'authentication': fake_arn(service='iam', generate_account_id=True),
                    'billing_source': self.fake.word(),
                    'customer_name': self.fake.word(),
                    'provider_type': 'AWS',
                    'schema_name': self.fake.word(),
                }
            )

    def test_initializer(self):
        """Test to init"""
        orchestrator = Orchestrator()

        if len(orchestrator._accounts) != 3:
            self.fail("Unexpected number of test accounts")

        for account in orchestrator._accounts:
            if account.get('provider_type') == AMAZON_WEB_SERVICES:
                self.assertEqual(
                    account.get('authentication'), self.aws_provider_resource_name
                )
                self.assertEqual(
                    account.get('billing_source'), self.aws_test_billing_source
                )
                self.assertEqual(account.get('customer_name'), self.schema)
            elif account.get('provider_type') == OPENSHIFT_CONTAINER_PLATFORM:
                self.assertEqual(
                    account.get('authentication'), self.ocp_provider_resource_name
                )
                self.assertEqual(
                    account.get('billing_source'), self.ocp_test_billing_source
                )
                self.assertEqual(account.get('customer_name'), self.schema)
            elif account.get('provider_type') == AZURE:
                pass
            else:
                self.fail('Unexpected provider')

        if len(orchestrator._polling_accounts) != 1:
            self.fail("Unexpected number of listener test accounts")

        for account in orchestrator._polling_accounts:
            if account.get('provider_type') == AMAZON_WEB_SERVICES:
                self.assertEqual(
                    account.get('authentication'), self.aws_provider_resource_name
                )
                self.assertEqual(
                    account.get('billing_source'), self.aws_test_billing_source
                )
                self.assertEqual(account.get('customer_name'), self.schema)
            elif account.get('provider_type') == AZURE:
                pass
            else:
                self.fail('Unexpected provider')

    @patch(
        'masu.external.report_downloader.ReportDownloader._set_downloader',
        return_value=FakeDownloader,
    )
    @patch(
        'masu.external.accounts_accessor.AccountsAccessor.get_accounts', return_value=[]
    )
    def test_prepare_no_accounts(self, mock_downloader, mock_accounts_accessor):
        """Test downloading cost usage reports."""
        orchestrator = Orchestrator()
        reports = orchestrator.prepare()

        self.assertIsNone(reports)

    @patch.object(AccountsAccessor, 'get_accounts')
    def test_init_all_accounts(self, mock_accessor):
        """Test initializing orchestrator with forced billing source."""
        mock_accessor.return_value = self.mock_accounts
        orchestrator_all = Orchestrator()
        self.assertEqual(orchestrator_all._accounts, self.mock_accounts)

    @patch.object(AccountsAccessor, 'get_accounts')
    def test_init_with_billing_source(self, mock_accessor):
        """Test initializing orchestrator with forced billing source."""
        mock_accessor.return_value = self.mock_accounts

        fake_source = random.choice(self.mock_accounts)

        individual = Orchestrator(fake_source.get('billing_source'))
        self.assertEqual(len(individual._accounts), 1)
        found_account = individual._accounts[0]
        self.assertEqual(
            found_account.get('billing_source'), fake_source.get('billing_source')
        )

    @patch.object(AccountsAccessor, 'get_accounts')
    def test_init_all_accounts_error(self, mock_accessor):
        """Test initializing orchestrator accounts error."""
        mock_accessor.side_effect = AccountsAccessorError('Sample timeout error')
        try:
            Orchestrator()
        except Exception:
            self.fail('unexpected error')

    @patch.object(ExpiredDataRemover, 'remove')
    @patch(
        'masu.processor.orchestrator.remove_expired_data.apply_async', return_value=True
    )
    def test_remove_expired_report_data(self, mock_task, mock_remover):
        """Test removing expired report data."""
        expected_results = [
            {
                'account_payer_id': '999999999',
                'billing_period_start': '2018-06-24 15:47:33.052509',
            }
        ]
        mock_remover.return_value = expected_results

        expected = 'INFO:masu.processor.orchestrator:Expired data removal queued - customer: acct10001, Task ID: {}'
        # unset disabling all logging below CRITICAL from masu/__init__.py
        logging.disable(logging.NOTSET)
        with self.assertLogs('masu.processor.orchestrator', level='INFO') as logger:
            orchestrator = Orchestrator()
            results = orchestrator.remove_expired_report_data()
            self.assertTrue(results)
            self.assertEqual(len(results), 2)
            async_id = results.pop().get('async_id')
            self.assertIn(expected.format(async_id), logger.output)

    @patch.object(AccountsAccessor, 'get_accounts')
    @patch.object(ExpiredDataRemover, 'remove')
    @patch(
        'masu.processor.orchestrator.remove_expired_data.apply_async', return_value=True
    )
    def test_remove_expired_report_data_no_accounts(
        self, mock_task, mock_remover, mock_accessor
    ):
        """Test removing expired report data with no accounts."""
        expected_results = [
            {
                'account_payer_id': '999999999',
                'billing_period_start': '2018-06-24 15:47:33.052509',
            }
        ]
        mock_remover.return_value = expected_results
        mock_accessor.return_value = []

        orchestrator = Orchestrator()
        results = orchestrator.remove_expired_report_data()

        self.assertEqual(results, [])

    @patch('masu.processor.orchestrator.AccountLabel', spec=True)
    @patch('masu.processor.orchestrator.ProviderStatus', spec=True)
    @patch(
        'masu.processor.orchestrator.get_report_files.apply_async', return_value=True
    )
    def test_prepare_w_status_valid(self, mock_task, mock_accessor, mock_labeler):
        """Test that Orchestrator.prepare() works when status is valid."""
        mock_labeler().get_label_details.return_value = (True, True)

        mock_accessor().is_valid.return_value = True
        mock_accessor().is_backing_off.return_value = False

        orchestrator = Orchestrator()
        orchestrator.prepare()
        mock_task.assert_called()

    @patch('masu.processor.orchestrator.ProviderStatus', spec=True)
    @patch(
        'masu.processor.orchestrator.get_report_files.apply_async', return_value=True
    )
    def test_prepare_w_status_invalid(self, mock_task, mock_accessor):
        """Test that Orchestrator.prepare() is skipped when status is invalid."""
        mock_accessor.is_valid.return_value = False
        mock_accessor.is_backing_off.return_value = False

        orchestrator = Orchestrator()
        orchestrator.prepare()
        mock_task.assert_not_called()

    @patch('masu.processor.orchestrator.ProviderStatus', spec=True)
    @patch(
        'masu.processor.orchestrator.get_report_files.apply_async', return_value=True
    )
    def test_prepare_w_status_backoff(self, mock_task, mock_accessor):
        """Test that Orchestrator.prepare() is skipped when backing off."""
        mock_accessor.is_valid.return_value = False
        mock_accessor.is_backing_off.return_value = True

        orchestrator = Orchestrator()
        orchestrator.prepare()
        mock_task.assert_not_called()
