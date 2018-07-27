#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""AWS utility functions."""

import re

import boto3
from dateutil.relativedelta import relativedelta

from masu.util import common as utils


def get_assume_role_session(arn, session='MasuSession'):
    """
    Assume a Role and obtain session credentials for the given role.

    Args:
        arn (AwsArn): Amazon Resource Name
        session (String): A session name

    Usage :
        session = get_assume_role_session(session='ExampleSessionName',
                                          arn='arn:aws:iam::012345678901:role/my-role')
        client = session.client('sqs')

    See: https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html
    """
    client = boto3.client('sts')
    response = client.assume_role(RoleArn=str(arn), RoleSessionName=session)
    return boto3.Session(
        aws_access_key_id=response['Credentials']['AccessKeyId'],
        aws_secret_access_key=response['Credentials']['SecretAccessKey'],
        aws_session_token=response['Credentials']['SessionToken'],
        region_name='us-east-1')


def get_cur_report_definitions(role_arn, session=None):
    """
    Get Cost Usage Reports associated with a given RoleARN.

    Args:
        role_arn     (String) RoleARN for AWS session
    """
    if not session:
        session = get_assume_role_session(role_arn)
    cur_client = session.client('cur')
    defs = cur_client.describe_report_definitions()
    report_defs = defs.get('ReportDefinitions', [])
    return report_defs


def get_cur_report_names_in_bucket(role_arn, s3_bucket, session=None):
    """
    Get Cost Usage Reports associated with a given RoleARN.

    Args:
        role_arn     (String) RoleARN for AWS session

    Returns:
        ([String]): List of Cost Usage Report Names

    """
    report_defs = get_cur_report_definitions(role_arn, session)
    report_names = []
    for report in report_defs:
        if s3_bucket == report['S3Bucket']:
            report_names.append(report['ReportName'])
    return report_names


def month_date_range(for_date_time):
    """
    Get a formatted date range string for the given date.

    Date range is aligned on the first day of the current
    month and ends on the first day of the next month from the
    specified date.

    Args:
        for_date_time (DateTime): The starting datetime object

    Returns:
        (String): "YYYYMMDD-YYYYMMDD", example: "19701101-19701201"

    """
    start_month = for_date_time.replace(day=1, second=1, microsecond=1)
    end_month = start_month + relativedelta(months=+1)
    timeformat = '%Y%m%d'
    return '{}-{}'.format(start_month.strftime(timeformat),
                          end_month.strftime(timeformat))


def get_assembly_id_from_cur_key(key):
    """
    Get the assembly ID from a cost and usage report key.

    Args:
        key (String): Full key for a cost and usage report location.
        example: /koku/20180701-20180801/882083b7-ea62-4aab-aa6a-f0d08d65ee2b/koku-1.csv.gz

    Returns:
        (String): "Assembly ID UUID"
        example: "882083b7-ea62-4aab-aa6a-f0d08d65ee2b"

    """
    assembly_id = utils.extract_uuids_from_string(key)
    assembly_id = assembly_id.pop() if assembly_id else None

    return assembly_id


def get_local_file_name(cur_key):
    """
    Return the local file name for a given cost usage report key.

    If an assemblyID is present in the key, it will prepend it to the filename.

    Args:
        cur_key (String): reportKey value from manifest file.
        example:
        With AssemblyID: /koku/20180701-20180801/882083b7-ea62-4aab-aa6a-f0d08d65ee2b/koku-1.csv.gz
        Without AssemblyID: /koku/20180701-20180801/koku-Manifest.json

    Returns:
        (String): file name for the local file,
                example:
                With AssemblyID: "882083b7-ea62-4aab-aa6a-f0d08d65ee2b-koku-1.csv.gz"
                Without AssemblyID: "koku-Manifest.json"

    """
    s3_filename = cur_key.split('/')[-1]
    assembly_id = get_assembly_id_from_cur_key(cur_key)
    local_file_name = f'{assembly_id}-{s3_filename}' if assembly_id else f'{s3_filename}'

    return local_file_name


# pylint: disable=too-few-public-methods
class AwsArn(object):
    """
    Object representing an AWS ARN.

    See also:
        https://docs.aws.amazon.com/general/latest/gr/aws-arns-and-namespaces.html

    General ARN formats:
        arn:partition:service:region:account-id:resource
        arn:partition:service:region:account-id:resourcetype/resource
        arn:partition:service:region:account-id:resourcetype:resource

    Example ARNs:
        <!-- Elastic Beanstalk application version -->
        arn:aws:elasticbeanstalk:us-east-1:123456789012:environment/My App/foo
        <!-- IAM user name -->
        arn:aws:iam::123456789012:user/David
        <!-- Amazon RDS instance used for tagging -->
        arn:aws:rds:eu-west-1:123456789012:db:mysql-db
        <!-- Object in an Amazon S3 bucket -->
        arn:aws:s3:::my_corporate_bucket/exampleobject.png

    """

    arn_regex = re.compile(r'^arn:(?P<partition>\w+):(?P<service>\w+):'
                           r'(?P<region>\w+(?:-\w+)+)?:'
                           r'(?P<account_id>\d{12})?:(?P<resource_type>[^:/]+)'
                           r'(?P<resource_separator>[:/])?(?P<resource>.*)')

    partition = None
    service = None
    region = None
    account_id = None
    resource_type = None
    resource_separator = None
    resource = None

    def __init__(self, arn):
        """
        Parse ARN string into its component pieces.

        Args:
            arn (str): Amazon Resource Name

        """
        self.arn = arn
        match = self.arn_regex.match(arn)

        if not match:
            raise SyntaxError('Invalid ARN: {0}'.format(arn))

        for key, val in match.groupdict().items():
            setattr(self, key, val)

    def __repr__(self):
        """Return the ARN itself."""
        return self.arn
