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
"""Test the status API."""

from collections import namedtuple
from unittest.mock import ANY, Mock, patch

from django.urls import reverse
from django.test import TestCase

from api.status.model import Status

class StatusModelTest(TestCase):
    """Tests against the status functions."""

    def setUp(self):
        """Create test case setup."""
        self.status_info = None
        status_count = Status.objects.count()
        if status_count == 0:
            self.status_info = Status.objects.create()
            self.status_info.save()
        else:
            self.status_info = Status.objects.get(pk=1)

    @patch('os.environ')
    def test_commit_with_env(self, mock_os):
        """Test the commit method via environment."""
        expected = 'buildnum'
        mock_os.get.return_value = expected
        result = self.status_info.commit
        self.assertEqual(result, expected)

    @patch('subprocess.check_output')
    def test_commit_with_subprocess(self, mock_subprocess):
        """Test the commit method via subprocess."""
        expected = 'buildnum'
        mock_subprocess.return_value = expected
        result = self.status_info.commit
        self.assertEqual(result, expected)

    @patch('platform.uname')
    def test_platform_info(self, mock_platform):
        """Test the platform_info method."""
        platform_record = namedtuple('Platform', ['os', 'version'])
        a_plat = platform_record('Red Hat', '7.4')
        mock_platform.return_value = a_plat
        result = self.status_info.platform_info
        self.assertEqual(result['os'], 'Red Hat')
        self.assertEqual(result['version'], '7.4')

    @patch('sys.version')
    def test_python_version(self, mock_sys_ver):
        """Test the python_version method."""
        expected = 'Python 3.6'
        mock_sys_ver.replace.return_value = expected
        result = self.status_info.python_version
        self.assertEqual(result, expected)

    @patch('sys.modules')
    def test_modules(self, mock_modules):
        """Test the modules method."""
        expected = {'module1': 'version1',
                    'module2': 'version2'}
        mod1 = Mock(__version__='version1')
        mod2 = Mock(__version__='version2')
        mock_modules.items.return_value = (('module1', mod1),
                                           ('module2', mod2))
        result = self.status_info.modules
        self.assertEqual(result, expected)

    @patch('api.status.model.logger.info')
    def test_startup(self, mock_logger):  # pylint: disable=no-self-use
        """Test the startup method."""
        self.status_info.startup()
        mock_logger.assert_called_with(ANY, ANY)


class StatusViewTest(TestCase):
    """Tests the status view."""

    def setUp(self):
        """Create test case setup."""
        self.status_info = None
        status_count = Status.objects.count()
        if status_count == 0:
            self.status_info = Status.objects.create()
            self.status_info.save()
        else:
            self.status_info = Status.objects.get(pk=1)

    def test_status_endpoint(self):
        """Test the status endpoint."""
        url = reverse('server-status')
        response = self.client.get(url)
        json_result = response.json()
        self.assertEqual(json_result['api_version'], 1)
