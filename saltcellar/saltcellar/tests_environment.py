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
"""Test the environment utility."""

from collections import namedtuple
from unittest.mock import ANY, Mock, patch

from django.test import TestCase

from . import environment


class EnvironmentTest(TestCase):
    """Tests against the environment functions."""

    @patch('os.environ')
    def test_commit_with_env(self, mock_os):
        """Test the commit method via environment."""
        expected = 'buildnum'
        mock_os.get.return_value = expected
        result = environment.commit()
        self.assertEqual(result, expected)

    @patch('subprocess.check_output')
    def test_commit_with_subprocess(self, mock_subprocess):
        """Test the commit method via subprocess."""
        expected = 'buildnum'
        mock_subprocess.return_value = expected
        result = environment.commit()
        self.assertEqual(result, expected)

    @patch('platform.uname')
    def test_platform_info(self, mock_platform):
        """Test the platform_info method."""
        platform_record = namedtuple('Platform', ['os', 'version'])
        a_plat = platform_record('Red Hat', '7.4')
        mock_platform.return_value = a_plat
        result = environment.platform_info()
        self.assertEqual(result['os'], 'Red Hat')
        self.assertEqual(result['version'], '7.4')

    @patch('sys.version')
    def test_python_version(self, mock_sys_ver):
        """Test the python_version method."""
        expected = 'Python 3.6'
        mock_sys_ver.replace.return_value = expected
        result = environment.python_version()
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
        result = environment.modules()
        self.assertEqual(result, expected)

    @patch('saltcellar.environment.logger.info')
    def test_startup(self, mock_logger):  # pylint: disable=no-self-use
        """Test the startup method."""
        environment.startup()
        mock_logger.assert_called_with(ANY, ANY)
