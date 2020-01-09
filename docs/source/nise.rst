======
nise
======
you can install nise with pip::
    
    pip install koku-nise

nise is a fake data generator. It allows you to control what is generated.
An example of what can be generated is found in the example_ocp_static_data.yml file::
    generators:
        -OCPGenerator:  # this name is found in the init file of the generator currently
        start_date: last_month
        nodes:
            - node:
            - node_name: alpha
            - cpu_cores: 10
            - memory_gig: 16
            - resource_id: 55555555 # used to match to AWS resources
            - cpu_usage:
                full_period: 1
            - mem_usage_gig: 
                full_period: 2
        

Note: tags in this file are akin to user defined tags in AWS
Note: If you don't set cost and rate, the generated cost and rate would be random each day.

There are example yamls are in the nise repo. 

=============
List of flags
=============
- :code:`--start-date [DATE]` generate data starting on this date, until the end date. If no end date is specified, the current date is the ending date.
- :code:`--ocp` use this flag if you are creating fake ocp data
- :code:`--ocp-cluster-id [STRING]` corresponds to the provider resource name. Any string can be used.
- :code:`--static-report-file [STRING]` the yaml file that will be used to configure nise, for example: :code:`example_ocp_static_data.yml`
- :code:`--insights-upload [STRING]` the destination directory that nise will store the generated data. For example: :code:`testing/pvc_dir/insights_local`

If you are generating Azure or AWS data, the :code:`--insights-upload` should be set to:
    - For aws: koku/testing/local_providers/aws_local
    - For Azure: koku/testing/local_providers/azure_local

=================
Nise walkthrough
=================
This is an example of using nise to generate static report. 
Run one of the following examples:
So this creates AWS data from this starting date:
nise --start-date 2018-06-03

this command creates:
nise --start-date 2018-06-20 --aws --aws-s3-bucket-name testbucket --aws-s3-report-name cpu_cores

how to create OCP data, and check that it's updated for specific provider:
nise --start-date 2018-06
The upload path matches where the data is 
under testing/pvc_dir/insights_local
Run this command::
    nise --insights-upload testing/pvc_dir/insights_local --static-report-file example_ocp_static_data.yml --ocp --ocp-cluster-id test-001

The data should get copied into the testing/pvc_dir/insights_local directory. 

Next, create a provider by making a POST request to /api/cost-management/v1/providers/ with the following information:
    - Name: ProviderOCP
    - Type: OCP
    - Provider resource name: test-001 (that's the cluster ID in the data.yml)
    - Credentials: {} 
    - bucket:
    - data source: {} 
    The brackets are only needed in the django browseable API, you don't need empty brackets :code:`{}` in Postman or curl.


Send a GET request to the Masu download endpoint at masu. This causes masu to ingest the data into postgres.
http://localhost:5000/api/cost-management/v1/download/

In the :code:`koku_worker` logs, you'll may see logs that contain a provider_uuid which should be the same provider_uuid of the provider you created previously.
schema_name: act10001
provider: OCP
provider_uuid: same uuid as the provider we created.
After the data is ingested, the csv file is deleted from the testing/pvc_dir/insights_local directory.

You can check that the data was successfully uploaded by sending a GET request to one of the following endpoints:
    - api/cost-management/v1/reports/openshift/compute/
    - api/cost-management/v1/reports/openshift/memory/
    - api/cost-management/v1/reports/openshift/volumes/
    - api/cost-management/v1/reports/openshift/costs/ (this endpoint will not show any data until you add a cost model)

