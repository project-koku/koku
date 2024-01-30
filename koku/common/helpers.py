import hashlib
import typing as t

from django.db.utils import ProgrammingError
from django.utils.connection import ConnectionProxy


def get_function_hash(connection: ConnectionProxy, function_name: str) -> t.Optional[str]:
    with connection.cursor() as cursor:
        try:
            cursor.execute("SELECT pg_get_functiondef(%s::regproc)", (function_name,))
        except ProgrammingError:
            return

        result = cursor.fetchone()

    if result is not None:
        b_sql_function = "".join(result).encode("utf-8")
        sha256 = hashlib.sha256(b_sql_function)
        return sha256.hexdigest()
