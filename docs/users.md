# User Management

This section covers the customer owner, adding and removing users.

## Definitions

Project Koku uses terminology in certain ways to describe key concepts.
These are definitions of the term based on how they work within the
context of the Koku application.

**Customer** - An organization or entity that uses Project Koku for cost
management analysis.

**Source** - A cloud resource provider or cloud data provider. An entity that
produces cost and resource usage data. This could be a public or private
cloud.

**User** - A user of the Project Koku application. Users map to an
individual person or login with access to [customer](#customer) data.

## Development

Authentication for Koku is expected to be managed by an external
service. Authentication information is expected to be provided to Koku
through an HTTP header - `HTTP_X_RH_IDENTITY`.

For development purposes, if the environment variable `DEVELOPMENT=True`
is set, Koku will authenticate using its
[dev_middleware](https://github.com/project-koku/koku/blob/master/koku/koku/dev_middleware.py),
which bypasses authentication and authorizes any request as valid.

This is an example for making authenticated HTTP requests to the Koku
API when `DEVELOPMENT=True`. :

    #!/bin/bash
    HOST='localhost'
    IDENTITY=$(echo '{"identity":{"account_number":"10001","user":{"username":"test_customer","email":"koku-dev@example.com"}}}' | base64 | tr -d '\n')
    curl -g -H "HTTP_X_RH_IDENTITY: ${IDENTITY}" 'http://'${HOST}'/api/v1/reports/inventory/aws/instance-type/'
