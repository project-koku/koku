import logging
import os
import pkgutil
import time
from abc import ABCMeta
from abc import abstractmethod
from datetime import datetime
from typing import ClassVar

from django.db import connection
from django.db import OperationalError
from jinjasql import JinjaSql
from pydantic import BaseModel

from api.common import log_json
from koku.database_exc import get_extended_exception_by_type

LOG = logging.getLogger(__name__)


class BaseSQLRunner(BaseModel, metaclass=ABCMeta):
    @property
    @abstractmethod
    def template_name(self):
        pass

    @classmethod
    def get_sql_template(cls):
        sql = pkgutil.get_data("masu.database", cls.template_name)
        return sql.decode("utf-8")

    def get_sql_params(self) -> dict:
        """Return the parameters for the SQL query."""
        return self.model_dump()

    @abstractmethod
    def prepare_query(self, source, data) -> str:
        """Prepare the SQL query with the given parameters."""
        pass

    @abstractmethod
    def execute(cls, schema: str, *, sql_params: dict | None = None) -> None:
        """Run the given SQL statement."""
        pass


class PostgresSQLRunner(BaseSQLRunner):
    prepare_query: ClassVar = JinjaSql(param_style="pyformat").prepare_query

    def execute(self, schema: str, *, sql_params: dict | None = None) -> None:
        sql_params = self.get_sql_params()
        LOG.warning("\n\nTHESE ARE THE SQL PARAMS: %s\n\n", sql_params)

        sql, params = self.prepare_query(self.get_sql_template(), self.get_sql_params())
        with connection.cursor() as cursor:
            cursor.db.set_schema(schema)
            t1 = time.time()
            try:
                cursor.execute(sql, params=params)
            except OperationalError as exc:
                db_exc = get_extended_exception_by_type(exc)
                LOG.warning(log_json(os.getpid(), msg=str(db_exc), context=db_exc.as_dict()))
                raise db_exc from exc

        running_time = time.time() - t1
        LOG.info(log_json(msg=f"finished {self.template_name}", running_time=running_time))


class TrinoSQLRunner(BaseSQLRunner):
    pass


class ReportingAWSCatagorySummary(PostgresSQLRunner):
    template_name: ClassVar[str] = "sql/reporting_awscategory_summary.sql"

    schema: str
    bill_ids: list[int]
    start_date: datetime
    end_date: datetime
