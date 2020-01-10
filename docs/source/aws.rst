
===========================
How to ingest data from AWS
===========================
1. Add AWS credentials to the `.env` file.

AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=

You'll need to set those environment variables with your AWS access and secret key. And then you can call docker-compose up

=========================
How to Create a Provider
=========================
Send a POST request to ``http://<your_host>:8000/api/cost-management/v1/providers/``
With the content:
Provider Resource Name: <whatever your arn is>

    curl -d '{"name": "AWSProvider", "type": "AWS", "authentication": {"provider_resource_name": "$ARN"}, "billing_source": {"bucket": "$BUCKET"}}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8000/api/cost-management/v1/providers/

Note:
   - The `$ARN` variable will need to be replace with your provider resource name. Example, `arn:aws:iam::01234567890:my_aws_role`.
   - The `$BUCKET` variable will need to be replaced with your bucket name. Example, `koku_bucket`.

You should receive a 200 range response confirming that the Provider was created.

=============
Trigger Masu
=============

Send a GET request to ``http://<your_host>:5000/api/cost-management/v1/download/`` That *should* trigger the worker to load the data into the DB.

You may want to check the logs to see if the loading is occuring:

    docker-compose logs -f koku-server koku-worker

If you see this error:

    Provider skipped: da56f23c-100e-4158-8544-0a146a9dc64d Valid: True Backing off: True

Then check the api_providerstatus table to see what the error message is.
