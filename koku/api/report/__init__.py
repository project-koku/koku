# noqa
from api.provider.models import Provider
from api.report.all.openshift.provider_map import OCPAllProviderMap
from api.report.aws.provider_map import AWSProviderMap
from api.report.azure.openshift.provider_map import OCPAzureProviderMap
from api.report.azure.provider_map import AzureProviderMap
from api.report.ocp.provider_map import OCPProviderMap
from api.report.ocp_aws.provider_map import OCPAWSProviderMap

provider_pm_map = {
    "aws": (Provider.PROVIDER_AWS, AWSProviderMap),
    "azure": (Provider.PROVIDER_AZURE, AzureProviderMap),
    "ocp": (Provider.PROVIDER_OCP, OCPProviderMap),
    "ocp_aws": (Provider.OCP_AWS, OCPAWSProviderMap),
    "ocp_azure": (Provider.OCP_AZURE, OCPAzureProviderMap),
    "ocp_all": (Provider.OCP_ALL, OCPAllProviderMap),
}

provider_set_map = {
    "aws": {"aws"},
    "azure": {"azure"},
    "ocp": {"ocp"},
    "ocp_aws": {"ocp", "aws"},
    "ocp_azure": {"ocp", "azure"},
}
