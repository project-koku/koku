#
# Copyright 2018 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Sources application configuration module."""
import logging
from koku.env import ENVIRONMENT

from django.apps import AppConfig
#from sources.kafka_listener import initialize_kafka_listener

LOG = logging.getLogger(__name__)

class SourcesConfig(AppConfig):
    """Sources application configuration."""

    name = 'sources'

    def ready(self):
        """Determine if app is ready on application startup."""
        # import pdb; pdb.set_trace()
        is_sources = ENVIRONMENT.bool('SOURCES', default=False)
        print(str(is_sources))
        if is_sources:
            LOG.info('Starting SourcesKafka handler')
            #initialize_kafka_listener()
