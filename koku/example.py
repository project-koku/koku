from masu.external.downloader.gcp.gcp_report_downloader import GCPReportDownloader
from masu.database.provider_collector import ProviderCollector

provider_uuid = "7a1d6ba6-be2a-4913-af0a-2794140ab41f"
account = "org1234567"

with ProviderCollector() as collector:
    all_providers = collector.get_provider_uuid_map()
    provider = all_providers.get(str(provider_uuid))

kwargs = {
    "provider_uuid": provider_uuid,
    "account": account,
    "credentials": provider.authentication.credentials
}

data_source = provider.billing_source.data_source

GCPReportDownloader(customer_name=account, data_source=data_source, **kwargs).get_manifest_context_for_date("2022-07-1")