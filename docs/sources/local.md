# Adding a Local Source

This section describes the local sources that are used for development
and testing purposes. Local sources give Koku the ability to access test
data without requiring a dependency on an external service, such as AWS
S3 or a pre-existing OpenShift cluster (OKD).

## AWS Local Source

These steps will allow you to configure a local source for a Koku
instance deployed into an OpenShift environment.

1.  Deploy an OKD cluster: `make oc-up`

2.  Deploy Koku into the cluster: `make oc-create-koku`

3.

    Add a [persistent volume](https://docs.okd.io/latest/dev_guide/persistent_volumes.html) to the Koku pod

    :   Mount point: `/tmp/koku`

4.  Wait for Koku to redeploy to verify the persistent volume is
    available.

5.  Use Nise to generate test data.

6.  Upload the test data to the Koku pod:
    `oc rsync <data_on_host> <koku_pod>:/tmp/masu`

7.

    Create the local source in the Koku app.

    :   Source Resource Name:
        `arn:aws:iam::111111111111:role/LocalAWSSource` Source Type:
        `AWS` Bucket: `/tmp/koku/local/<report_name>`

Once configured, you should be able to use Masu\'s download endpoint to
queue tasks to download and process the local source\'s data.
