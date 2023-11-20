#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Updater base for OpenShift on Cloud Infrastructures."""
import logging

from django.db import IntegrityError

from api.common import log_json
from api.provider.models import Provider
from api.provider.models import ProviderInfrastructureMap
from koku.cache import get_cached_infra_map
from koku.cache import set_cached_infra_map
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
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
        self._provider: Provider = provider
        self._provider_uuid = str(self._provider.uuid)
        self._manifest = manifest
        self._date_accessor = DateAccessor()

    def get_infra_map_from_providers(self):
        """Check a provider for an existing OpenShift/Cloud relationship.

        Returns:
            infra_map (list[tuple]): A list of provider relationships
                of the form [(OpenShift Provider UUID,
                                Infrastructure Provider UUID,
                                Infrastructure Provider Type)]

        """
        infra_map = {}
        if self._provider.type == Provider.PROVIDER_OCP:
            if not self._provider.infrastructure:
                return infra_map
            if self._provider.infrastructure.infrastructure_type == Provider.PROVIDER_OCP:
                # OCP infra is invalid, so delete these entries from the providerinframap.
                # The foreign key relation sets the infra on the provider to null when the map is deleted.
                ProviderInfrastructureMap.objects.filter(id=self._provider.infrastructure.id).delete()
                return infra_map
            infra_map[self._provider_uuid] = (
                str(self._provider.infrastructure.infrastructure_provider.uuid),
                self._provider.infrastructure.infrastructure_type,
            )
        elif self._provider.type in Provider.CLOUD_PROVIDER_LIST:
            ps = Provider.objects.filter(infrastructure__infrastructure_provider__uuid=self._provider.uuid)
            for provider in ps:
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
        cache_infra_map = get_cached_infra_map(self._schema, self._provider.type, self._provider_uuid)
        if cache_infra_map:
            LOG.info(
                log_json(
                    msg="retrieved matching infra map from cache",
                    provider_uuid=self._provider_uuid,
                    schema=self._schema,
                )
            )
            return cache_infra_map
        infra_map = {}
        if self._provider.type == Provider.PROVIDER_OCP:
            with OCPReportDBAccessor(self._schema) as accessor:
                infra_map = accessor.get_ocp_infrastructure_map_trino(
                    start_date,
                    end_date,
                    ocp_provider_uuid=self._provider_uuid,
                )
        elif self._provider.type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
            with OCPReportDBAccessor(self._schema) as accessor:
                infra_map = accessor.get_ocp_infrastructure_map_trino(
                    start_date,
                    end_date,
                    aws_provider_uuid=self._provider_uuid,
                )
        elif self._provider.type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
            with OCPReportDBAccessor(self._schema) as accessor:
                infra_map = accessor.get_ocp_infrastructure_map_trino(
                    start_date,
                    end_date,
                    azure_provider_uuid=self._provider_uuid,
                )
        elif self._provider.type in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
            with OCPReportDBAccessor(self._schema) as accessor:
                infra_map = accessor.get_ocp_infrastructure_map_trino(
                    start_date,
                    end_date,
                    gcp_provider_uuid=self._provider_uuid,
                )

        # Save to DB
        self.set_provider_infra_map(infra_map)

        set_cached_infra_map(self._schema, self._provider.type, self._provider_uuid, infra_map)
        return infra_map

    def set_provider_infra_map(self, infra_map):
        """Use the infra map to map providers to infrastructures.

        The infra_map comes from created in _generate_ocp_infra_map_from_sql.
        """
        for key, infra_tuple in infra_map.items():
            provider = Provider.objects.filter(uuid=key).first()
            if not provider:
                continue
            try:
                infra, _ = ProviderInfrastructureMap.objects.get_or_create(
                    infrastructure_provider_id=infra_tuple[0], infrastructure_type=infra_tuple[1]
                )
            except IntegrityError:
                infra = ProviderInfrastructureMap.objects.filter(
                    infrastructure_provider_id=infra_tuple[0], infrastructure_type=infra_tuple[1]
                ).first()
            if not infra:
                continue
            provider.set_infrastructure(infra)

    def get_openshift_and_infra_providers_lists(self, infra_map):
        """Return two lists.

        One of OpenShift provider UUIDS,
        the other of infrastructrure provider UUIDS.

        """
        openshift_provider_uuids = list(infra_map)
        infra_provider_uuids = [value[0] for value in infra_map.values()]
        return openshift_provider_uuids, infra_provider_uuids
