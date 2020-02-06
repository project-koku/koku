#
# Copyright 2019 Red Hat, Inc.
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
"""Masu utility methods."""
import watchtower
from boto3.session import Session
from botocore.exceptions import ClientError
from masu.config import Config


def setup_cloudwatch_logging(logger):
    """Add Cloud Watch log handler if appropriate."""
    if not (Config.CW_AWS_ACCESS_KEY_ID and Config.CW_AWS_SECRET_ACCESS_KEY):
        logger.info("CloudWatch logging disabled due to missing access key")
        return

    try:
        session = Session(
            aws_access_key_id=Config.CW_AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.CW_AWS_SECRET_ACCESS_KEY,
            region_name=Config.CW_AWS_REGION,
        )
        handler = watchtower.CloudWatchLogHandler(
            boto3_session=session, log_group=Config.CW_LOG_GROUP, stream_name=Config.NAMESPACE
        )
        logger.addHandler(handler)
    except ClientError as cerr:
        logger.error("CloudWatch logging setup failed: %s", cerr)
