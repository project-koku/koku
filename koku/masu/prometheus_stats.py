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
"""Prometheus Stats."""
from prometheus_client import CollectorRegistry, Counter, multiprocess, start_http_server


WORKER_REGISTRY = CollectorRegistry()
multiprocess.MultiProcessCollector(WORKER_REGISTRY)

GET_REPORT_ATTEMPTS_COUNTER = Counter('get_report_files_attempts_count',
                                      'Number of ingest attempts',
                                      ['provider_type'],
                                      registry=WORKER_REGISTRY)
REPORT_FILE_DOWNLOAD_ERROR_COUNTER = Counter('report_file_download_error_count',
                                             'Number of report file download errors',
                                             ['provider_type'],
                                             registry=WORKER_REGISTRY)
PROCESS_REPORT_ATTEMPTS_COUNTER = Counter('process_report_attempts_count',
                                          'Number of report files attempted processing',
                                          ['provider_type'],
                                          registry=WORKER_REGISTRY)
PROCESS_REPORT_ERROR_COUNTER = Counter('process_report_error_count',
                                       'Number of report files attempted processing',
                                       ['provider_type'],
                                       registry=WORKER_REGISTRY)
REPORT_SUMMARY_ATTEMPTS_COUNTER = Counter('report_summary_attempts_count',
                                          'Number of report summary attempts',
                                          ['provider_type'],
                                          registry=WORKER_REGISTRY)
CHARGE_UPDATE_ATTEMPTS_COUNTER = Counter('charge_update_attempts_count',
                                         'Number of derivied cost update attempts',
                                         registry=WORKER_REGISTRY)

COST_SUMMARY_ATTEMPTS_COUNTER = Counter('cost_summary_attempts_count',
                                        'Number of cost summary update attempts',
                                        registry=WORKER_REGISTRY)

KAFKA_CONNECTION_ERRORS_COUNTER = Counter('kafka_connection_errors',
                                          'Number of Kafka connection errors',
                                          registry=WORKER_REGISTRY)


def initialize_prometheus_exporter():
    """Start Prometheus stats HTTP server."""
    start_http_server(9999, registry=WORKER_REGISTRY)
