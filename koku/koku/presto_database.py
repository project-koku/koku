import re
from decimal import Decimal

POSITIONAL_VARS = re.compile("%s")
NAMED_VARS = re.compile(r"%(.+)s")
EOT = re.compile(r",\s*\)$")  # pylint: disable=anomalous-backslash-in-string


def type_transform(v):
    if v is None:
        return "null"
    elif isinstance(v, (int, float, Decimal, complex, bool, list)):
        return str(v)
    elif isinstance(v, tuple):
        return EOT.sub(")", str(v))
    else:
        return f"'{str(v)}'"


def has_params(sql):
    return bool(POSITIONAL_VARS.search(sql)) or bool(NAMED_VARS.search(sql))


def sql_mogrify(sql, params=None):
    """
    Cheap version of psycopg2.Cursor.mogrify method. Does not inject type casting.
    None type will be converted to "null"
    int, float, Decimal, complex, bool types will be converted to string
    All other types will be converted to strings surrounded by single-quote characters
    Params:
        sql (str) : SQL formatted for the driver using %s or %(name)s placeholders
    """
    if params is not None and has_params(sql):
        if isinstance(params, dict):
            mog_params = {k: type_transform(v) for k, v in params.items()}
        else:
            mog_params = tuple(type_transform(p) for p in params)

        return sql % mog_params
    else:
        return sql
