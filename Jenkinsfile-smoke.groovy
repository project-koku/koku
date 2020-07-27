/*
* Requires: https://github.com/RedHatInsights/insights-pipeline-lib
*/

@Library("github.com/RedHatInsights/insights-pipeline-lib@v3") _

// This smoke job will run cost-management tests.
def appConfigs = [
    cost_management: [plugins: ["cost_management"]]
]

if (env.CHANGE_ID) {
    execSmokeTest (
        ocDeployerBuilderPath: "hccm/koku",
        ocDeployerComponentPath: "hccm",
        ocDeployerServiceSets: "ingress,platform-mq,sources,hccm",
        // iqePlugins: ["iqe-cost-management-plugin"],
        pytestMarker: "cost_smoke",
        // local settings file
        configFileCredentialsId: "hccm_smoke_settings_local_yaml",
        appConfigs: appConfigs,
    )
}
