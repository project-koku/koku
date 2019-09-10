"""Tests for celery tasks."""
from datetime import date, datetime
from unittest.mock import call, patch

from masu.celery import tasks
from masu.test import MasuTestCase


class TestCeleryTasks(MasuTestCase):
    """Test cases for Celery tasks."""

    @patch('masu.celery.tasks.Orchestrator')
    def test_check_report_updates(self, mock_orchestrator):
        """Test that the scheduled task calls the orchestrator."""
        mock_orch = mock_orchestrator()
        tasks.check_report_updates()

        mock_orchestrator.assert_called()
        mock_orch.prepare.assert_called()

    @patch('masu.celery.tasks.Orchestrator')
    @patch('masu.external.date_accessor.DateAccessor.today')
    def test_remove_expired_data(self, mock_date, mock_orchestrator):
        """Test that the scheduled task calls the orchestrator."""
        mock_orch = mock_orchestrator()

        mock_date_string = '2018-07-25 00:00:30.993536'
        mock_date_obj = datetime.strptime(mock_date_string, '%Y-%m-%d %H:%M:%S.%f')
        mock_date.return_value = mock_date_obj

        tasks.remove_expired_data()

        mock_orchestrator.assert_called()
        mock_orch.remove_expired_report_data.assert_called()

    @patch('masu.celery.tasks.Orchestrator')
    @patch('masu.celery.tasks.query_and_upload_to_s3')
    @patch('masu.external.date_accessor.DateAccessor.today')
    def test_upload_normalized_data(self, mock_date, mock_upload, mock_orchestrator):
        """Test that the scheduled task uploads the correct normalized data."""

        test_export_setting = {
            'provider': 'test',
            'table_name': 'test',
            'sql': 'test_sql'
        }
        schema_name = 'acct10001'

        mock_date.return_value = date(2015, 1, 5)

        mock_orchestrator.get_accounts.return_value = [{'schema_name': schema_name}], []
        current_month_start = date(2015, 1, 1)
        current_month_end = date(2015, 1, 31)
        prev_month_start = date(2014, 12, 1)
        prev_month_end = date(2014, 12, 31)

        call_curr_month = call(schema_name, test_export_setting, (current_month_start, current_month_end))
        call_prev_month = call(schema_name, test_export_setting, (prev_month_start, prev_month_end))

        with patch('masu.celery.tasks.table_export_settings', [test_export_setting]):
            tasks.upload_normalized_data()
            mock_upload.assert_has_calls([call_curr_month, call_prev_month])

        mock_date.return_value = date(2012, 3, 31)
        current_month_start = date(2012, 3, 1)
        current_month_end = date(2012, 3, 31)
        prev_month_start = date(2012, 2, 1)
        prev_month_end = date(2012, 2, 29)

        call_curr_month = call(schema_name, test_export_setting, (current_month_start, current_month_end))
        call_prev_month = call(schema_name, test_export_setting, (prev_month_start, prev_month_end))

        with patch('masu.celery.tasks.table_export_settings', [test_export_setting]):
            tasks.upload_normalized_data()
            mock_upload.assert_has_calls([call_curr_month, call_prev_month])
