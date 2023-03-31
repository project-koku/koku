# Controling Visibility of Resources

In certain cases you may not wish users to have access to all cost data,
but instead only data specific to their projects or organization. Using
role based access control you can limit the visibility of resources
involved in cost management reports. Role based access control utilizes
groups of which users are members. These groups can be associated with
one or more policies. A policy associates a group with a set of roles. A
role defines a permission and a set of resource definitions. By default
a user who is not an account administrator will not have access to data,
but instead must be granted access to resources. Account administrators
can view all data without any configuration within the role based access
control.

Reports involving Amazon Web Services can be scoped by usage account or
its account alias. For example if an administrator has configured eight
Amazon accounts (sources) specific to different organizations within the
company, but only wished a user to be able to see the data associated
with their organization/account; role based access control can be
utilized to filter the data set to only that specific account. This can
be accomplished by creating a group that encompasses the users for that
organization. A role can be defined that allows "read" permission on
the specified Amazon account. Lastly a policy can be created that
associates the group and role. Now any user in that group will have
visibility limited to just that Amazon account.

Reports involving OpenShift can be scoped by the cluster, node, and
project. In order to see report data users must have visibility to a
cluster. Visibility can be further limited by specifying nodes or
projects. For example an administrator might have two clusters
configured (one for pre-production and one for production) and they wish
to expose the cost of projects deployed on these clusters to the
associated development teams. Groups would be created for each
development team. Roles would be created to give "read" access to each
of the clusters but only the specific project. Lastly a policy would be
created to associate a specific group with the role that provides them
visibility to only their project.

Reports involving OpenShift running on Amazon Web Services require
visibility to be setup on both the Amazon account and the OpenShift
resources as described above.
