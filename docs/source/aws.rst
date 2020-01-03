
===========================
How to ingest data from AWS
===========================
1. Add AWS credentials to docker-compose

Docker-compose has two repeated lines:

AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=

You'll need to set those environment variables with your AWS access and secret key. And then you can call docker-compose up

=========================
How to Create a Provider
=========================
Send a POST request to ``http://<your_host>:8000/api/cost-management/v1/providers/``
With the content:
Provider Resource Name: <whatever your arn is> 
 
  http POST 0.0.0.0:8000/api/cost-management/v1/providers/ name='AWSProvider' type='AWS' \ authentication:='{"uuid": "e6d90e5a-feb9-472e-97f3-b96839206f4f","provider_resource_name": "arn:aws:iam::01234567890:my_aws_role"}' 
 
You should receive a 200 range response confirming that the Provider was created.

=============
Trigger Masu
=============

Send a GET request to `http://<your_host>:5000/api/cost-management/v1/download/` That _should_ trigger the worker to load the data into the DB.

You may want to check the logs to see if the loading is occuring:

`docker-compose logs -f koku-server koku-worker`

If you see this error:
`Provider skipped: da56f23c-100e-4158-8544-0a146a9dc64d Valid: True Backing off: True`
Then check the api_providerstatus table to see what the error message is.
