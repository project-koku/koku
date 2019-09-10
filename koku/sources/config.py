#
# Copyright 2019 Red Hat, Inc.
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
import os


class Config:
    """Configuration for service."""
    SOURCES_KAFKA_HOST = os.getenv('SOURCES_KAFKA_HOST', 'localhost')
    SOURCES_KAFKA_PORT = os.getenv('SOURCES_KAFKA_PORT', '29092')
    SOURCES_KAFKA_ADDRESS = f'{SOURCES_KAFKA_HOST}:{SOURCES_KAFKA_PORT}'
    SOURCES_TOPIC = os.getenv('SOURCES_KAFKA_TOPIC', 'platform.sources.event-stream')

    SOURCES_API_HOST = os.getenv('SOURCES_API_HOST', 'localhost')
    SOURCES_API_PORT = os.getenv('SOURCES_API_PORT', '3000')
    SOURCES_API_URL = f'http://{SOURCES_API_HOST}:{SOURCES_API_PORT}'
    SOURCES_API_PREFIX = os.getenv('SOURCES_API_PREFIX', '/api/v1.0')
    SOURCES_INTERNAL_API_PREFIX = os.getenv('SOURCES_INTERNAL_API_PREFIX', '/internal/v1.0')
    SOURCES_FAKE_HEADER = os.getenv('SOURCES_FAKE_HEADER', ("eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1i"
                                                            "ZXIiOiAiMTIzNDUiLCAiaW50ZXJuYWwiOiB7"
                                                            "Im9yZ19pZCI6ICI1NDMyMSJ9fX0="))
    KOKU_API_HOST = os.getenv('KOKU_API_HOST', 'localhost')
    KOKU_API_PORT = os.getenv('KOKU_API_PORT', '8000')
    KOKU_API_PATH_PREFIX = os.getenv('KOKU_API_PORT', '/api/cost-management/v1')
    KOKU_API_URL = f'http://{KOKU_API_HOST}:{KOKU_API_PORT}{KOKU_API_PATH_PREFIX}'
