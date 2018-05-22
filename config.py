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

"""Configuration loader for Masu application."""

import os


# pylint: disable=too-few-public-methods
class Config(object):
    """Configuration for app."""

    DEBUG = os.getenv('MASU_DEBUG', False)
    if isinstance(DEBUG, str) and DEBUG.lower() in ('f', 'false'):
        DEBUG = False

    # Database
    DB_ENGINE = os.getenv('DATABASE_ENGINE', 'sqlite')
    DB_NAME = os.getenv('DATABASE_NAME', 'masu')
    DB_USER = os.getenv('DATABASE_USER', 'masu')
    DB_PASSWORD = os.getenv('DATABASE_PASSWORD', 'masu')
    DB_HOST = os.getenv('DATABASE_HOST', 'localhost')
    DB_PORT = os.getenv('DATABASE_PORT', 5432)

    SQLALCHEMY_DATABASE_URI = \
        f'{DB_ENGINE}://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

    # Override for sqlite
    if DB_ENGINE == 'sqlite':
        SQLALCHEMY_DATABASE_URI = f'{DB_ENGINE}:///{DB_NAME}.db'

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SECRET_KEY = os.getenv('MASU_SECRET_KEY')
    if SECRET_KEY is None:
        raise ValueError('No secret key set for Masu application')

    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    # Data directory for processing incoming data
    TMP_DIR = '/var/tmp/masu'
