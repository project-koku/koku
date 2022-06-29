#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from datetime import date
from datetime import datetime
from decimal import Decimal
from json import JSONDecoder
from json import JSONEncoder

import ciso8601


TRANSCODE_TYPES = {
    datetime: "transcode_datetime",
    date: "transcode_date",
    Decimal: "transcode_decimal",
}
DECODE_TYPES = {
    "datetime": ciso8601.parse_datetime,
    "date": date.fromisoformat,
    "Decimal": Decimal,
}


class TypedJSONEncoder(JSONEncoder):
    """Encodes values of type Decimal/Date/DateTime in json serializable data for DB"""

    def default(self, o):
        if isinstance(o, tuple(TRANSCODE_TYPES)):
            return getattr(self, TRANSCODE_TYPES[type(o)])(o)
        else:
            return super().default(o)

    def transcode_datetime(self, o):
        return {"_py_type": "datetime", "value": str(o)}

    def transcode_date(self, o):
        return {"_py_type": "date", "value": str(o)}

    def transcode_decimal(self, o):
        return {"_py_type": "Decimal", "value": str(o)}


class TypedJSONDecoder(JSONDecoder):
    """Decodes values in the DB into the appropriate type format Decimal/Date/DateTime"""

    def __init__(self, *args, **kwargs):
        kwargs["object_hook"] = self.object_hook
        super().__init__(*args, **kwargs)

    def object_hook(self, o):
        if "_py_type" in o and o["_py_type"] in DECODE_TYPES:
            return DECODE_TYPES[o["_py_type"]](o["value"])
        return o
