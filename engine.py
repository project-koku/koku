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
"""SQLAlchemy database engine creation."""
from tempfile import NamedTemporaryFile

import sqlalchemy

from masu.config import Config


def _create_engine_kwargs(db_ca_cert):
    """Create the kwargs for the database engine.

    Args:
        db_ca_cert (String): "Root CA Certificate for DB SSL verification"
    Returns:
        (Dict): "Engine arguments"
        (String): "Certificate file path"
    """
    kwargs = {
        'client_encoding': 'utf8',
        'pool_size': Config.SQLALCHEMY_POOL_SIZE
    }
    cert_path = None
    if db_ca_cert:
        temp_cert_file = NamedTemporaryFile(delete=False, mode='w', suffix='pem')
        cert_path = temp_cert_file.name
        with open(temp_cert_file.name, mode='w') as cert_file:
            cert_file.write(db_ca_cert)
        kwargs['connect_args'] = {
            'sslmode': 'verify-full',
            'sslrootcert': temp_cert_file.name
        }
    return kwargs, cert_path


def create_engine():
    """Create a database engine to manage DB connections.

    Args:
        None
    Returns:
        (sqlalchemy.engine.base.Engine): "SQLAlchemy engine object",
        (sqlalchemy.sql.schema.MetaData): "SQLAlchemy engine metadata"
    """
    kwargs, _ = _create_engine_kwargs(Config.DB_CA_CERT)
    return sqlalchemy.create_engine(
        Config.SQLALCHEMY_DATABASE_URI,
        **kwargs
    )


DB_ENGINE = create_engine()
