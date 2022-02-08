#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Updater base for OpenShift on Cloud Infrastructures."""
import logging

from api.provider.models import Provider
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external.date_accessor import DateAccessor

LOG = logging.getLogger(__name__)


class OCPCloudUpdaterBase:
    """Base class for OpenShift on cloud infrastructure operations."""

    def __init__(self, schema, provider, manifest):
        """Initialize the class.

        Args:
            schema   (str) The customer schema to associate with.
            provider (Provider db object) Database object for Provider.
            manifest (str) The manifest to work with.

        Returns:
            None

        """
        self._schema = schema
        self._provider = provider
        self._provider_uuid = str(self._provider.uuid)
        self._manifest = manifest
        self._date_accessor = DateAccessor()

    def get_infra_map(self):
        """Check a provider for an existing OpenShift/Cloud relationship.

        Returns:
            infra_map (list[tuple]): A list of provider relationships
                of the form [(OpenShift Provider UUID,
                                Infrastructure Provider UUID,
                                Infrastructure Provider Type)]

        """
        infra_map = {}
        with ProviderDBAccessor(self._provider.uuid) as provider_accessor:
            if self._provider.type == Provider.PROVIDER_OCP:
                infra_type = provider_accessor.get_infrastructure_type()
                infra_provider_uuid = provider_accessor.get_infrastructure_provider_uuid()
                if infra_provider_uuid:
                    infra_map[self._provider_uuid] = (infra_provider_uuid, infra_type)
            elif self._provider.type in Provider.CLOUD_PROVIDER_LIST:
                associated_providers = provider_accessor.get_associated_openshift_providers()
                for provider in associated_providers:
                    infra_map[str(provider.uuid)] = (self._provider_uuid, self._provider.type)
        return infra_map

    def _generate_ocp_infra_map_from_sql(self, start_date, end_date):
        """Get the OCP on X infrastructure map.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns:
            infra_map (dict) The OCP infrastructure map.

        """
        infra_map = {}
        if self._provider.type == Provider.PROVIDER_OCP:
            with OCPReportDBAccessor(self._schema) as accessor:
                infra_map = accessor.get_ocp_infrastructure_map(
                    start_date, end_date, ocp_provider_uuid=self._provider_uuid
                )
        elif self._provider.type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
            with OCPReportDBAccessor(self._schema) as accessor:
                infra_map = accessor.get_ocp_infrastructure_map(
                    start_date, end_date, aws_provider_uuid=self._provider_uuid
                )
        elif self._provider.type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
            with OCPReportDBAccessor(self._schema) as accessor:
                infra_map = accessor.get_ocp_infrastructure_map(
                    start_date, end_date, azure_provider_uuid=self._provider_uuid
                )

        # Save to DB
        self.set_provider_infra_map(infra_map)

        return infra_map

    def _generate_ocp_infra_map_from_sql_trino(self, start_date, end_date):
        """Get the OCP on X infrastructure map.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns:
            infra_map (dict) The OCP infrastructure map.

        """
        infra_map = {}
        if self._provider.type == Provider.PROVIDER_OCP:
            with OCPReportDBAccessor(self._schema) as accessor:
                infra_map = accessor.get_ocp_infrastructure_map_trino(
                    start_date, end_date, ocp_provider_uuid=self._provider_uuid
                )
        elif self._provider.type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
            with OCPReportDBAccessor(self._schema) as accessor:
                infra_map = accessor.get_ocp_infrastructure_map_trino(
                    start_date, end_date, aws_provider_uuid=self._provider_uuid
                )
        elif self._provider.type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
            with OCPReportDBAccessor(self._schema) as accessor:
                infra_map = accessor.get_ocp_infrastructure_map_trino(
                    start_date, end_date, azure_provider_uuid=self._provider_uuid
                )
        elif self._provider.type in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
            with OCPReportDBAccessor(self._schema) as accessor:
                infra_map = accessor.get_ocp_infrastructure_map_trino(
                    start_date, end_date, gcp_provider_uuid=self._provider_uuid
                )

        # Save to DB
        self.set_provider_infra_map(infra_map)

        return infra_map

    def set_provider_infra_map(self, infra_map):
        """Use the infra map to map providers to infrastructures.

        The infra_map comes from created in _generate_ocp_infra_map_from_sql.
        """
        for key, infra_tuple in infra_map.items():
            with ProviderDBAccessor(key) as provider_accessor:
                provider_accessor.set_infrastructure(
                    infrastructure_provider_uuid=infra_tuple[0], infrastructure_type=infra_tuple[1]
                )

    def get_openshift_and_infra_providers_lists(self, infra_map):
        """Return two lists.

        One of OpenShift provider UUIDS,
        the other of infrastructrure provider UUIDS.

        """
        openshift_provider_uuids = [key for key in infra_map]
        infra_provider_uuids = [value[0] for value in infra_map.values()]
        return openshift_provider_uuids, infra_provider_uuids
