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
"""Initializer for external module."""

# Provider Types
AMAZON_WEB_SERVICES = 'AWS'

# Compression formats
UNCOMPRESSED = 'PLAIN'
GZIP_COMPRESSED = 'GZIP'

# Notificaton Definitions
AWS_SNS_HEADER_MSG_TYPE = 'X-Amz-Sns-Message-Type'
AWS_SNS_HEADER_TOPIC_ARN = 'X-Amz-Sns-Topic-Arn'

# Valid AWS Regions from https://docs.aws.amazon.com/general/latest/gr/rande.html
AWS_REGIONS = ['us-east-2',
               'us-east-1',
               'us-west-1',
               'us-west-2',
               'ap-south-1',
               'ap-northeast-2',
               'ap-northeast-3',
               'ap-southeast-1',
               'ap-southeast-2',
               'ap-northeast-1',
               'ca-central-1',
               'cn-north-1',
               'cn-northwest-1',
               'eu-central-1',
               'eu-west-1',
               'eu-west-2',
               'eu-west-3',
               'sa-east-1']
