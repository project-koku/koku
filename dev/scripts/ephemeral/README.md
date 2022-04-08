# ephemeral
A wrapper to bonfire to run local repository on ephemeral cluster

### Prerequisits
1. public repository in [quay.io](https://quay.io/)
2. Install Openshift cli ([get oc command here](https://docs.openshift.com/container-platform/4.7/cli_reference/openshift_cli/getting-started-cli.html))

### Setup
1. Go to koku project directory
    ```
    cd ${KOKU_HOME}
    pipenv install --dev
    pipenv shell "pre-commit install
    ```
2. Set the required environment variables. (examples below)
   ```
   export KOKU_HOME=~/github/koku
   export EPHEMERAL_USERNAME=testuser
   export QUAY_REPO=quay.io/testuser/koku
   export AWS_ACCESS_KEY_ID_EPH="[YOUR AWS ACCESS KEY]"
   export AWS_SECRET_ACCESS_KEY_EPH="[YOUR SECRET ACCESS KEY]"
     ```
3. log into the ephemeral env
    [HERE](https://oauth-openshift.apps.c-rh-c-eph.8p0c.p1.openshiftapps.com/oauth/token/display)
   1. Once logged in through the UI you can cut and paste the oc login command into your terminal.
      example:
    ```
    oc login --token=sha256~<*** some token ***> --server=https://api.c-rh-c-eph.8p0c.p1.openshiftapps.com:6443
    ```

### Reserving a namespace

1. reserve a namespace (example of 24 hours (defaults to 48 hours if no hours are given)
    ```
   make ephemeral-reserve-ns hours="48h"
   ```
2. You can check your namespace
    ```
   make ephemeral-get-ns
   ```
3. You can view the pods (you should not see any resources at this point)
    ```
   make ephemeral-get-pods
   ```

### Building and Deploying an image
1. build image from local repository
    ```
   make ephemeral-build-image
   ```
2. deploy image built image
    ```
   make ephemeral-deploy-image
   ```
3. watch as pods come spin up(at this point you should start seeing koku specific pods, similar to running locally)
    ```
   make ephemeral-get-pods
   ```
### Using port forwarding
1. start forwarding all ports from local host to ephemeral env
    ```
   make ephemeral-forward-ports
   ```
2. stop forwarding all ports from local host to ephemeral env
    ```
   make ephemeral-stop-forward-ports
   ```

### Releasing a namespace
1. to release the current namespace you are working inmake eph
    ```
   make ephemeral-release-ns
   ```
