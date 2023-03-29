# Developer Tools

This section describes tooling and features included in Koku to assist
developers contributing to Koku.

## Environment Variables

Koku makes use of environment variables to configure features and
application capabilities.

In the repository, there is an `.env.example` file with sample
environment settings. The `.env` file is used by Django\'s tools as well
as Koku\'s scripting. It is the recommended way to configure your local
development environment settings.

This section documents environment variables that may be of interest to
developers.

`DEVELOPMENT=(True|False)` - Enables development features. Not for
production use. `DEVELOPMENT_IDENTITY=(JSON)` - A JSON Object
representing a User

## Authentication

When `DEVELOPMENT` is not set, Koku expects to use an external service
to handle authentication and access control for most API endpoints.

When `DEVELOPMENT` is set, the development middleware is enabled. This
allows passing in custom identity information into Koku for development
and testing purposes using the `DEVELOPMENT_IDENTITY` variable.

Example DEVELOPMENT_IDENTITY object:

    {
        "identity": {
            "account_number": "10001",
            "type": "User",
            "user": {
                "username": "user_dev",
                "email": "user_dev@foo.com",
                "is_org_admin": False
                "access": {
                    "aws.account": {
                        "read": ["1234567890AB", "234567890AB1"]
                    }
                    "gcp.account": {
                        "read": ["*"]
                    }
                    "gcp.project": {
                        "read": ["*"]
                    }
                    "azure.subscription_guid": {
                        "read": ["*"]
                    }
                    "openshift.cluster": {
                        "read": ["*"]
                    }
                    "openshift.project": {
                        "read": ["*"]
                    }
                    "openshift.node": {
                        "read": ["*"]
                    }
                }
            },
        },
        "entitlements": {"cost_management": {"is_entitled": True}},
    }

::: note
::: title
Note
:::

This example is pretty-printed for readability. When setting the
enviroment variable, it should be collapsed to one single line.
:::
