Adding a Local Provider
#######################

This section describes the local providers that are used for development and
testing purposes. Local providers give Koku the ability to access test data
without requiring a dependency on an external service, such as AWS S3 or a
pre-existing OpenShift cluster (OKD).

AWS Local Provider
******************
These steps will allow you to configure a local provider for a Koku instance
deployed into an OpenShift environment.

#. Deploy an OKD cluster: ``make oc-up``
#. Deploy Koku into the cluster: ``make oc-create-koku``
#. Add a `persistent volume <https://docs.okd.io/latest/dev_guide/persistent_volumes.html>`_ to the Koku pod
    Mount point: ``/tmp/koku``

4. Wait for Koku to redeploy to verify the persistent volume is available.
#. Use Nise to generate test data.
#. Upload the test data to the Koku pod: ``oc rsync <data_on_host> <koku_pod>:/tmp/masu``
#. Create the local provider in the Koku app.
    Provider Resource Name: ``arn:aws:iam::111111111111:role/LocalAWSProvider``
    Provider Type: ``AWS``
    Bucket: ``/tmp/koku/local/<report_name>``

Once configured, you should be able to use Masu's download endpoint to queue
tasks to download and process the local provider's data.
