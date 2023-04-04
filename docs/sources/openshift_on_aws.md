# Running OpenShift on AWS

If sources have been successfully configured for AWS and OpenShift and
the OpenShift cluster is running on AWS, then the AWS cost and usage
related to running the OpenShift cluster can be automatically tracked.
By default, AWS compute usage and costs are tracked by associating the
Amazon EC2 instance id with the OpenShift node running on that instance.
Further association can be made by associating AWS tags with OpenShift
labels.

# Matching AWS Tags with OpenShift Labels

Resource tagging can also be used to identify AWS resources associated
with an OpenShift cluster running on AWS. The matched AWS resources need
not be running explicitly within the OpenShift cluster, but can be any
AWS resource that allows tagging. For example an AWS RDS instance would
not run inside OpenShift, but the cost of running RDS may be associated
with OpenShift projects in the cluster. If an AWS user-defined tag
matches an OpenShift label, that RDS instance usage and cost can be
assocaited with the OpenShift cluster.

AWS documents the process of creating user-defined tags and activating
them for cost and usage reporting here:
[https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/custom-tags.html](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/custom-tags.html/).

Information about creating OpenShift labels can be found here:
[https://docs.okd.io/latest/architecture/core_concepts/pods_and_services.html#labels](https://docs.okd.io/latest/architecture/core_concepts/pods_and_services.html#labels/).

In order for an AWS tag to match an OpenShift label it must meet one of
the following criteria.

 1. The lowercase version of the AWS tag key must match the lowercase
    version of the OpenShift label key. The lowercase version of the
    AWS tag value must match the lowercase version of the OpenShift
    label value.

     The following examples would meet this requirment.

        (AWS key:value) == (OpenShift key:value)
        environment:production == environment:production
        Environment:production == environment:production
        Environment:Production == environment:PRODUCTION

 1. The lowercase version of the AWS tag key is
    `openshift_cluster` and the lowercase value of the tag
    matches the lowercase OpenShift cluster name.

    The following example would meet this requirment.

        (AWS key:value) (OpenShift cluster name)
        Openshift_cluster:Openshift_1 == Openshift_1

 1. The lowercase version of the AWS tag key is
    `openshift_project` and the lowercase value of the tag
    matches a lowercase OpenShift project name in the cluster.

    The following example would meet this requirment.

        (AWS key:value) (OpenShift project name)
        Openshift_Project:Cost_Management == Cost_Management

 1. The lowercase version of the AWS tag key is
    `openshift_node` and the lowercase value of the tag
    matches a lowercase OpenShift node name in the cluster.

    The following example would meet this requirment.

        (AWS key:value) (OpenShift node name)
        Openshift_node:compute_1 == COMPUTE_1

If an AWS resource tag matches with multiple OpenShift projects, the
cost and usage of that resource are split evenly between the matched
projects. Note that this is not the case with AWS compute resources that
are matched via the instance id - node relationship. In that case cost
and usage are broken down using information about a project's resource
consumption within the OpenShift environment.
