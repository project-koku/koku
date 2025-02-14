#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging

import boto3
from django.core.management.base import BaseCommand

import koku.trino_database as trino_db

LOG = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        catalog_id = boto3.client("sts").get_caller_identity()["Account"]
        glue = boto3.client("glue", region_name="us-east-1")

        db_paginator = glue.get_paginator("get_databases")
        for db_list in db_paginator.paginate(CatalogId=catalog_id, AttributesToGet=["NAME"]):
            LOG.info(db_list)
            for db in db_list["DatabaseList"]:
                db_name: str = db["Name"]
                if not (db_name.startswith("acct") or db_name.startswith("org")):
                    continue
                table_paginator = glue.get_paginator("get_tables")
                for table_list in table_paginator.paginate(
                    CatalogId=catalog_id, DatabaseName=db_name, AttributesToGet=["NAME"]
                ):
                    for table in table_list["TableList"]:
                        with trino_db.connect(schema=catalog_id) as conn:
                            cur = conn.cursor()
                            sql = f"""CALL system.sync_partition_metadata('{db_name}', '{table["Name"]}', 'FULL')"""
                            LOG.info(sql)
                            cur.execute(sql)
