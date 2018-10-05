User Management
===============

This section covers the customer owner, adding and removing users, email on-boarding and user preferences.

Definitions
-----------
Project Koku uses terminology in certain ways to describe key concepts. These are definitions of the term based on how they work within the context of the Koku and Masu applications.

.. _customer:

Customer: An organization or entity that uses Project Koku for cost management analysis.

.. _customer owner:

Customer Owner: A user_ that is responsible for management of a customer_. Customer owners have administrative privileges over Customer data.

.. _provider:

Provider: A cloud resource provider or cloud data provider. An entity that produces cost and resource usage data.

.. _user:

User - A user of the Project Koku application. Users map to an individual person or login.

Customer Owner
--------------

When a customer is created, a user is also created associated with the customer. This initial user is referred to as the customer owner and has special privileges. A customer owner has the following privileges:

- Adding new users
- Removing users
- Deleting providers

Adding and Removing Users
-------------------------

In order to allow more users to access the cost data, the `customer owner`_ can add more users to their customer. In order to add a user_ you must supply a username and valid email for the associated user. A password can be optionally provided, if a password is not provided one will be generated for the user_. When the user_ is created they will receive an email to assist with on-boarding, see the section on `Email On-boarding`_ for more information.

Customer owners may remove a user's access. Only a `customer owner`_ has the privilege to grant or revoke access. Only the associated user_ data and preferences will be removed when a user_ is removed; any provider_, such as Amazon Web Services accounts, added by a removed user_ will continue to remain, but can be removed by the `customer owner`_ at any point.

Email On-boarding
-----------------

When a user_ is added to a customer_ they will receive an email with a link to the service website. The link provided in the email will enable the user_ to reset their password so they can log into web interface or utilize the API. The password reset link provided contains a unique identifier for the user_ and a reset token. The reset token will expire in 24 hours. When resetting the password the existing password cannot be reused. Once the reset token is used to change the password it will expire.

User Preferences
----------------

When a user_ is created they will have default preferences. These preferences determine how currency, timezone, and locale will be displayed in the Koku UI.

The default preferences are ::

- **Currency:** USD
- **Timezone:** UTC
- **Locale:** English United States *(en_US)*

Development
-----------

Authentication for Koku is expected to be managed by an external service.  Authentication information is expected to be provided to Koku through an HTTP header - ``HTTP_X_RH_IDENTITY``.

For development purposes, if the environment variable ``DEVELOPMENT=True`` is set, Koku will authenticate using its `dev_middleware <https://github.com/project-koku/koku/blob/master/koku/koku/dev_middleware.py>`_, which bypasses authentication and authorizes any request as valid.

This is an example for making authenticated HTTP requests to the Koku API when ``DEVELOPMENT=True``. ::

   #!/bin/bash
   HOST='localhost'
   IDENTITY=$(echo '"identity":{"org_id":"20001","account_number":"10001","username":"test_customer","email":"koku-dev@example.com"}' | base64 | tr -d '\n')
   curl -g -H "HTTP_X_RH_IDENTITY: ${IDENTITY}" 'http://'${HOST}'/api/v1/reports/inventory/instance-type/'
