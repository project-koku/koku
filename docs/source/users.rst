User Management
===============

This section covers the customer owner, adding and removing users, email on-boarding and user preferences.

Customer Owner
##############

When a customer is created, a user is also created associated with the customer. This initial user is referred to as the customer owner and has special privileges. A customer owner has the following privileges:

- Adding new users
- Removing users
- Deleting providers

Adding and Removing Users
#########################

In order to allow more people to access the cost data, the customer owner can add more users to their customer. In order to add a user you must supply a username and valid email for the associated user. A password can be optionally provided, if a password is not provided one will be generated for the user. When the user is created they will receive an email to assist with on-boarding, see the section on `Email On-boarding`_ for more information.

Customer owners may remove a user's access. Only customer owners have the privilege to grant or revoke access. Only the associated user data and preferences will be removed when a user is removed; any providers, such as Amazon Web Services accounts, added by a removed user will continue to remain, but can be removed by the customer owner at any point.

Email On-boarding
#################

When a user is added to a customer they will receive an email with a link to the service website. The link provided in the email will enable the user to reset their password so they can log into web interface or utilize the API. The password reset link provided contains a unique identifier for the user and the reset token. The reset token will expire in 24 hours. When resetting the password the existing password cannot be specified. Once the reset token is used to change the password it cannot be reused again.

User Preferences
################

When a user is created they will have default preferences initialized around currency, timezone, and locale as described below:

- **Currency:** USD
- **Timezone:** UTC
- **Locale:** English United States *(en_US)*

The user preferences control the language and output format of the cost data. Changing the user preferences will alter the viewed data.
