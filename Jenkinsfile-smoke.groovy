/*
* Requires: https://github.com/RedHatInsights/insights-pipeline-lib
*/

@Library("github.com/RedHatInsights/insights-pipeline-lib") _


if (env.CHANGE_ID) {
    runSmokeTest (
        ocDeployerBuilderPath: "hccm/hccm",
        ocDeployerComponentPath: "hccm/hccm",
        ocDeployerServiceSets: "hccm,platform,platform-mq",
        iqePlugins: ["hccm-plugin"],
        pytestMarker: "hccm_smoke",
    )
}
