from datetime import datetime
from unittest.mock import Mock, patch
from masu.celery.tasks import check_report_updates, remove_expired_data
from masu.test import MasuTestCase


class TestCeleryTasks(MasuTestCase):
    """Test cases for Celery tasks."""

    @patch('masu.celery.tasks.Orchestrator')
    def test_check_report_updates(self, mock_orchestrator):
        """Test that the scheduled task calls the orchestrator."""
        mock_orch = mock_orchestrator()
        check_report_updates()

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

        remove_expired_data()

        mock_orchestrator.assert_called()
        mock_orch.remove_expired_report_data.assert_called()
