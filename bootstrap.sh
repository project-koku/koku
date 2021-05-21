set -exv

# log in to ephemeral cluster
oc login --token=$OC_LOGIN_TOKEN --server=$OC_LOGIN_SERVER

export APP_ROOT=$(pwd)
export WORKSPACE=${WORKSPACE:-$APP_ROOT}  # if running in jenkins, use the build's workspace
export BONFIRE_ROOT=${WORKSPACE}/bonfire
export CICD_ROOT=${BONFIRE_ROOT}/cicd
export IMAGE_TAG=$(git rev-parse --short=7 HEAD)
export GIT_COMMIT=$(git rev-parse HEAD)

# TODO: create custom jenkins agent image that has a lot of this stuff pre-installed
export LANG=en_US.utf-8
export LC_ALL=en_US.utf-8

python3 -m venv .bonfire_venv
source .bonfire_venv/bin/activate

pip install --upgrade pip setuptools wheel
pip install --upgrade 'crc-bonfire>=1.1.5'

# clone repo to download cicd scripts
git clone https://github.com/RedHatInsights/bonfire.git $BONFIRE_ROOT
